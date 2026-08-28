# ============================================================
# Setad Jang — Developer/CI command shortcuts
# ============================================================
# این Makefile یک entrypoint واحد برای quality gates پروژه است.
# هر دستور باید هم local و هم CI-friendly باشد.

PYTHON ?= python
MANAGE := $(PYTHON) manage.py
SCHEMA_OUTPUT ?= /tmp/setad-jang-schema-check.yaml

PROD_CHECK_ENV := \
	ALLOWED_HOSTS=example.com \
	CACHE_BACKEND=redis \
	CORS_ALLOWED_ORIGINS=https://example.com \
	DATABASE_ENGINE=postgres \
	POSTGRES_DB=setadjang \
	POSTGRES_USER=setadjang \
	POSTGRES_PASSWORD=strong-postgres-password \
	POSTGRES_HOST=127.0.0.1 \
	POSTGRES_PORT=5432 \
	SECRET_KEY=realistic-production-secret-key-with-more-than-fifty-characters-2026 \
	SECURE_SSL_REDIRECT=True

.PHONY: help install lock lock-check lint format format-check structure structure-check check deploy-check migrations-check schema-check schema-update test coverage pip-check pip-audit bandit secrets-scan security verify verify-fast docker-up docker-down

help:
	@printf '%s\n' 'Setad Jang commands:'
	@printf '%s\n' '  make install           Install production + dev dependencies'
	@printf '%s\n' '  make lint              Run Ruff lint checks'
	@printf '%s\n' '  make format-check      Verify Ruff formatting (CI gate)'
	@printf '%s\n' '  make format            Apply Ruff formatting'
	@printf '%s\n' '  make check             Run Django system check'
	@printf '%s\n' '  make deploy-check      Run Django deployment check with safe env'
	@printf '%s\n' '  make migrations-check  Ensure migrations are up to date'
	@printf '%s\n' '  make schema-check      Validate OpenAPI schema and detect drift'
	@printf '%s\n' '  make schema-update     Regenerate committed schema.yaml'
	@printf '%s\n' '  make structure         Regenerate STRUCTURE.md'
	@printf '%s\n' '  make structure-check   Detect STRUCTURE.md drift'
	@printf '%s\n' '  make lock              Regenerate dependency lock files'
	@printf '%s\n' '  make lock-check        Detect dependency lock drift'
	@printf '%s\n' '  make test              Run full pytest suite'
	@printf '%s\n' '  make coverage          Run full pytest suite with coverage threshold'
	@printf '%s\n' '  make security          Run dependency/SAST/secrets security gate'
	@printf '%s\n' '  make verify            Run full local/CI quality gate'

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .

# بخش [tool.ruff.format] در pyproject.toml با دقت تنظیم شده بود ولی هیچ گیتی
# اجرایش نمی‌کرد، و نتیجه‌اش این بود که ۵۵٪ فایل‌ها با استاندارد فرمت خودِ
# پروژه همخوان نبودند. این هدف، فرمت را از «توصیه» به «قرارداد» تبدیل می‌کند.
format-check:
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff format .

check:
	$(MANAGE) check

deploy-check:
	$(PROD_CHECK_ENV) $(MANAGE) check --deploy --settings=config.settings.production

migrations-check:
	$(MANAGE) makemigrations --check --dry-run

# اعتبارسنجی به‌تنهایی کافی نیست: schema.yaml در مخزن commit می‌شود و اگر
# سریالایزری عوض شود بدون اینکه فایل بازتولید شود، CI سبز می‌ماند و اسناد
# API بی‌صدا از کد جدا می‌افتند. این هدف علاوه بر validate، خروجی تازه را با
# نسخهٔ commit‌شده diff می‌کند.
schema-check:
	$(MANAGE) spectacular --file $(SCHEMA_OUTPUT) --validate
	@diff -u schema.yaml $(SCHEMA_OUTPUT) > /dev/null 2>&1 || { \
		echo ''; \
		echo 'ERROR: schema.yaml با کد همگام نیست. «make schema-update» را اجرا و نتیجه را commit کن.'; \
		echo ''; \
		diff -u schema.yaml $(SCHEMA_OUTPUT) | head -40; \
		exit 1; \
	}

schema-update:
	$(MANAGE) spectacular --file schema.yaml --validate

# STRUCTURE.md یک سند تولیدشده است. قبلاً دستی commit می‌شد و کهنه شده بود؛
# حالا بازتولیدپذیر است و drift آن در CI گرفته می‌شود.
structure:
	$(PYTHON) scripts/generate_structure.py

structure-check:
	$(PYTHON) scripts/generate_structure.py --check

pip-check:
	$(PYTHON) -m pip check

lock:
	$(PYTHON) scripts/generate_locks.py

lock-check:
	$(PYTHON) scripts/generate_locks.py --check

pip-audit:
	$(PYTHON) -m pip_audit -r requirements.txt -r requirements-dev.txt --progress-spinner off

bandit:
	$(PYTHON) -m bandit -q -r apps config -x '*/migrations/*,*/tests/*,*/tests.py' -s B101,B105

secrets-scan:
	detect-secrets scan --baseline .secrets.baseline --all-files --force-use-all-plugins --exclude-files '(^\.git/|^media/|^staticfiles/|^schema\.yaml|^\.secrets\.baseline$$|^\.pytest_cache/|^\.ruff_cache/)'

security: pip-audit bandit secrets-scan

test:
	$(PYTHON) -m pytest -q

coverage:
	$(PYTHON) -m pytest --cov=apps --cov=config --cov-report=term --cov-fail-under=82 -q

verify-fast: lint format-check check migrations-check schema-check structure-check

verify: pip-check lock-check security lint format-check check deploy-check migrations-check schema-check structure-check coverage

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down
