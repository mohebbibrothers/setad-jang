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

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir=/wheels -r requirements.txt


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
CMD ["sh", "-c", "gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --workers ${GUNICORN_WORKERS:-3} \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/v1/health/ready/" || exit 1
