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
	CACHE_BACKEND=locmem \
	CORS_ALLOWED_ORIGINS=https://example.com \
	DATABASE_ENGINE=postgres \
	POSTGRES_DB=setadjang \
	POSTGRES_USER=setadjang \
	POSTGRES_PASSWORD=strong-postgres-password \
	POSTGRES_HOST=127.0.0.1 \
	POSTGRES_PORT=5432 \
	SECRET_KEY=realistic-production-secret-key-with-more-than-fifty-characters-2026 \
	SECURE_SSL_REDIRECT=True

.PHONY: help install lint check deploy-check migrations-check schema-check schema-update test pip-check pip-audit bandit secrets-scan security verify verify-fast docker-up docker-down

help:
	@printf '%s\n' 'Setad Jang commands:'
	@printf '%s\n' '  make install           Install production + dev dependencies'
	@printf '%s\n' '  make lint              Run Ruff lint checks'
	@printf '%s\n' '  make check             Run Django system check'
	@printf '%s\n' '  make deploy-check      Run Django deployment check with safe env'
	@printf '%s\n' '  make migrations-check  Ensure migrations are up to date'
	@printf '%s\n' '  make schema-check      Validate OpenAPI schema into /tmp'
	@printf '%s\n' '  make schema-update     Regenerate committed schema.yaml'
	@printf '%s\n' '  make test              Run full pytest suite'
	@printf '%s\n' '  make security          Run dependency/SAST/secrets security gate'
	@printf '%s\n' '  make verify            Run full local/CI quality gate'

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .

check:
	$(MANAGE) check

deploy-check:
	$(PROD_CHECK_ENV) $(MANAGE) check --deploy --settings=config.settings.production

migrations-check:
	$(MANAGE) makemigrations --check --dry-run

schema-check:
	$(MANAGE) spectacular --file $(SCHEMA_OUTPUT) --validate

schema-update:
	$(MANAGE) spectacular --file schema.yaml --validate

pip-check:
	$(PYTHON) -m pip check

pip-audit:
	$(PYTHON) -m pip_audit -r requirements.txt -r requirements-dev.txt --progress-spinner off

bandit:
	$(PYTHON) -m bandit -q -r apps config -x '*/migrations/*,*/tests/*,*/tests.py' -s B101,B105

secrets-scan:
	detect-secrets scan --baseline .secrets.baseline --all-files --force-use-all-plugins --exclude-files '(^\\.git/|^media/|^staticfiles/|^schema\\.yaml|^\\.secrets\\.baseline$$|^\\.pytest_cache/|^\\.ruff_cache/)'

security: pip-audit bandit secrets-scan

test:
	$(PYTHON) -m pytest -q

verify-fast: lint check migrations-check schema-check

verify: pip-check security lint check deploy-check migrations-check schema-check test

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down
