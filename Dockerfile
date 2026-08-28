# ============================================================
# Setad Jang — Production Dockerfile (multi-stage)
# ============================================================
# Stage 1 (builder): toolchain + ساخت wheels.
# Stage 2 (runtime): wheels + کد + entrypoint.sh + tini + gosu.
#
# Privilege model:
# - container به‌عنوان root شروع می‌شود تا entrypoint بتواند مالکیت
#   named volumes را correct کند.
# - سپس entrypoint با `gosu app` به user غیر-root drop می‌شود.
# - این الگو در image های رسمی stateful (Postgres/MySQL/Redis) استاندارد است.
#
# Network resilience:
# - Acquire::Retries و --fix-missing برای پایداری apt در شبکه‌های unreliable.
# ------------------------------------------------------------

ARG PYTHON_VERSION=3.14-slim


# ============================================================
# Stage 1 — builder
# ============================================================
FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' \
    > /etc/apt/apt.conf.d/80-retries

RUN apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        build-essential \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# از قفل کامل استفاده می‌شود، نه requirements.txt.
# requirements.txt وابستگی‌های غیرمستقیم را پین نمی‌کند، پس دو build از یک
# commit یکسان می‌توانند نسخه‌های متفاوتی بگیرند و image قابل بازتولید نباشد.
COPY requirements.txt requirements-lock.txt ./
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir=/wheels -r requirements-lock.txt


# ============================================================
# Stage 2 — runtime
# ============================================================
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=8000 \
    DEBIAN_FRONTEND=noninteractive \
    APP_USER=app \
    APP_GROUP=app

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' \
    > /etc/apt/apt.conf.d/80-retries

# runtime libs + tini + gosu (برای privilege drop در entrypoint)
RUN apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends --fix-missing \
        libjpeg62-turbo \
        zlib1g \
        curl \
        tini \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# کاربر غیر-root که در نهایت سرویس‌ها زیر آن اجرا می‌شوند
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --system --gid ${APP_GID} ${APP_GROUP} \
    && useradd --system --uid ${APP_UID} --gid ${APP_GROUP} --create-home --shell /usr/sbin/nologin ${APP_USER}

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

# entrypoint قبل از کد کپی می‌شود تا cache layer جدا و پایدار بماند
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# کپی کد پروژه
COPY . /app

# نکتهٔ حیاتی: `COPY . /app` فایل entrypoint را (با modeِ build context) دوباره
# بازنویسی می‌کند و chmodِ مرحلهٔ قبل را خنثی می‌سازد. اگر checkout شل اسکریپت را
# بدون بیت اجرایی داشته باشد (مثلاً بعد از `git reset --hard` وقتی mode در گیت
# قدیمی 644 بود)، ایمیج نهایی entrypoint غیراجرایی می‌گیرد و tini با
# «Permission denied» کرش‌لوپ می‌شود. بنابراین chmod اینجا، بعد از COPY، حتمی است.
RUN chmod +x /app/entrypoint.sh

# پوشه‌های runtime را از قبل بساز و owner را به app بده.
# داده روی named-volumeها در entrypoint مدیریت می‌شود.
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R ${APP_USER}:${APP_GROUP} /app

# عمداً USER ست نمی‌کنیم: entrypoint با root شروع می‌شود تا ownership
# volumeها را fix کند، سپس با gosu به app drop می‌شود.

EXPOSE 8000

# tini به‌عنوان init برای signal handling درست.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]

# CMD پیش‌فرض: gunicorn روی WSGI app.
#
# چرا gthread و نه sync
# ----------------------
# worker class پیش‌فرض gunicorn «sync» است، یعنی هر worker دقیقاً یک درخواست
# را در لحظه می‌گیرد. با ۳ worker سقف همزمانی کل سیستم ۳ درخواست است. این
# مدل با معماری I/O این پروژه سازگار نیست: تماس با درگاه پرداخت، پنل پیامک
# و سرویس revalidate فرانت‌اند می‌توانند ثانیه‌ها طول بکشند و در تمام آن مدت
# worker فقط منتظر شبکه است. سه کاربر همزمان روی درگاه کند یعنی کل سایت
# برای بقیه از دسترس خارج است.
#
# gthread با ۸ ریسمان روی هر worker همزمانی مؤثر را به ۲۴ می‌رساند بدون
# اینکه به monkey-patching (gevent/eventlet) نیاز باشد — که با درایور
# psycopg و کتابخانه‌های C این پروژه ریسک‌دار است.
#
# نکتهٔ ظرفیت دیتابیس: هر ریسمان connection مستقل خودش را می‌گیرد، پس سقف
# اتصال این سرویس workers × threads است (پیش‌فرض ۲۴). موقع بالا بردن این
# اعداد باید max_connections پستگرس و سهم celery هم با هم دیده شوند.
#
# exec لازم است
# --------------
# بدون exec، پوستهٔ sh به‌عنوان والد gunicorn باقی می‌ماند و SIGTERM را به
# فرزندش forward نمی‌کند؛ همان اشکالی که در entrypoint.sh هم برطرف شد.
# نتیجه‌اش این است که هر deploy به‌جای shutdown گریسفول با SIGKILL تمام
# می‌شود و درخواست‌های در حال پردازش — از جمله callback تأیید پرداخت — قطع
# می‌شوند.
#
# max-requests چرخهٔ بازیافت worker است و در برابر نشت تدریجی حافظه محافظت
# می‌کند؛ jitter از هم‌زمان شدن ری‌استارت همهٔ workerها جلوگیری می‌کند.
# worker-tmp-dir روی /dev/shm گذاشته شده تا heartbeat روی فایل‌سیستم‌های
# کند (مثل overlay روی دیسک شبکه) باعث کشته شدن اشتباهی worker نشود.
# access-logformat هم request_id ساخته‌شده در middleware را از هدر پاسخ
# می‌خواند تا لاگ gunicorn و لاگ اپلیکیشن قابل correlate باشند.
CMD ["sh", "-c", "exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --worker-class ${GUNICORN_WORKER_CLASS:-gthread} \
    --workers ${GUNICORN_WORKERS:-3} \
    --threads ${GUNICORN_THREADS:-8} \
    --timeout ${GUNICORN_TIMEOUT:-60} \
    --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT:-30} \
    --keep-alive ${GUNICORN_KEEPALIVE:-5} \
    --max-requests ${GUNICORN_MAX_REQUESTS:-1000} \
    --max-requests-jitter ${GUNICORN_MAX_REQUESTS_JITTER:-100} \
    --worker-tmp-dir /dev/shm \
    --access-logfile - \
    --error-logfile - \
    --access-logformat '%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\" rid=%({x-request-id}o)s dur=%(D)sus'"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/v1/health/ready/" || exit 1
