# Project Structure

Generated: 2026-05-19 19:10:08

```text
C:\Users\amirm\Desktop\setad_jang
├── apps/
│   ├── authentication/
│   │   ├── tests/
│   │   │   ├── __init__.py (50 B)
│   │   │   ├── test_normalizers.py (6.2 KB)
│   │   │   ├── test_otp.py (14.8 KB)
│   │   │   └── test_validators.py (9.9 KB)
│   │   ├── data/
│   │   │   ├── __init__.py (358 B)
│   │   │   └── disposable_email_domains.txt (74.7 KB)
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   └── __init__.py (0 B)
│   │   ├── migrations/
│   │   │   ├── __init__.py (0 B)
│   │   │   ├── 0001_initial.py (6.1 KB)
│   │   │   ├── 0002_add_phone_identifier_fields.py (2.0 KB)
│   │   │   ├── 0003_move_phone_to_user.py (3.1 KB)
│   │   │   ├── 0004_remove_profile_phone_number.py (359 B)
│   │   │   └── 0005_refactor_otpcode.py (2.4 KB)
│   │   ├── __init__.py (0 B)
│   │   ├── admin.py (3.6 KB)
│   │   ├── anti_abuse.py (5.2 KB)
│   │   ├── apps.py (282 B)
│   │   ├── choices.py (1.4 KB)
│   │   ├── filters.py (700 B)
│   │   ├── jwt_views.py (2.3 KB)
│   │   ├── managers.py (2.1 KB)
│   │   ├── models.py (8.9 KB)
│   │   ├── normalizers.py (8.6 KB)
│   │   ├── otp.py (15.1 KB)
│   │   ├── permissions.py (1.2 KB)
│   │   ├── providers.py (2.1 KB)
│   │   ├── selectors.py (1.4 KB)
│   │   ├── serializers.py (5.7 KB)
│   │   ├── services.py (7.5 KB)
│   │   ├── signals.py (354 B)
│   │   ├── throttles.py (1.8 KB)
│   │   ├── urls.py (1.6 KB)
│   │   ├── validators.py (9.5 KB)
│   │   └── views.py (30.6 KB)
│   ├── core/
│   │   ├── tests/
│   │   │   ├── __init__.py (40 B)
│   │   │   └── test_request_id_middleware.py (5.3 KB)
│   │   ├── health/
│   │   │   ├── __init__.py (0 B)
│   │   │   ├── checks.py (8.2 KB)
│   │   │   ├── serializers.py (4.4 KB)
│   │   │   ├── urls.py (553 B)
│   │   │   └── views.py (6.9 KB)
│   │   ├── migrations/
│   │   │   └── __init__.py (0 B)
│   │   ├── __init__.py (0 B)
│   │   ├── admin.py (30 B)
│   │   ├── apps.py (193 B)
│   │   ├── cache.py (5.3 KB)
│   │   ├── email_backends.py (3.1 KB)
│   │   ├── exceptions.py (5.2 KB)
│   │   ├── managers.py (639 B)
│   │   ├── middleware.py (6.0 KB)
│   │   ├── models.py (869 B)
│   │   ├── pagination.py (1.4 KB)
│   │   ├── permissions.py (907 B)
│   │   ├── responses.py (1.9 KB)
│   │   ├── schemas.py (3.4 KB)
│   │   └── views.py (27 B)
│   ├── public_reports/
│   │   ├── migrations/
│   │   │   ├── __init__.py (0 B)
│   │   │   └── 0001_initial.py (4.6 KB)
│   │   ├── __init__.py (0 B)
│   │   ├── admin.py (1002 B)
│   │   ├── apps.py (218 B)
│   │   ├── choices.py (277 B)
│   │   ├── filters.py (864 B)
│   │   ├── managers.py (174 B)
│   │   ├── models.py (2.9 KB)
│   │   ├── permissions.py (0 B)
│   │   ├── selectors.py (1.2 KB)
│   │   ├── serializers.py (4.3 KB)
│   │   ├── services.py (2.6 KB)
│   │   ├── tests.py (27 B)
│   │   ├── throttles.py (252 B)
│   │   ├── urls.py (1.6 KB)
│   │   ├── validators.py (712 B)
│   │   └── views.py (17.9 KB)
│   ├── tabyin/
│   │   ├── tests/
│   │   │   ├── __init__.py (46 B)
│   │   │   ├── test_selectors.py (7.5 KB)
│   │   │   ├── test_services_sync_async.py (7.8 KB)
│   │   │   ├── test_services_toggle.py (5.7 KB)
│   │   │   ├── test_sync_engine.py (8.8 KB)
│   │   │   ├── test_views_admin_sync.py (9.1 KB)
│   │   │   └── test_views_admin_toggle.py (5.0 KB)
│   │   ├── management/
│   │   │   ├── commands/
│   │   │   └── __init__.py (0 B)
│   │   ├── migrations/
│   │   │   ├── __init__.py (0 B)
│   │   │   └── 0001_initial.py (5.4 KB)
│   │   ├── providers/
│   │   │   ├── __init__.py (1.5 KB)
│   │   │   ├── base.py (1.2 KB)
│   │   │   └── mohtavanegar.py (2.8 KB)
│   │   ├── sync/
│   │   │   ├── __init__.py (0 B)
│   │   │   ├── client.py (6.1 KB)
│   │   │   ├── engine.py (13.0 KB)
│   │   │   ├── hasher.py (1.8 KB)
│   │   │   └── parser.py (4.9 KB)
│   │   ├── __init__.py (0 B)
│   │   ├── admin.py (2.6 KB)
│   │   ├── apps.py (197 B)
│   │   ├── choices.py (428 B)
│   │   ├── filters.py (3.1 KB)
│   │   ├── managers.py (2.6 KB)
│   │   ├── models.py (6.2 KB)
│   │   ├── selectors.py (6.9 KB)
│   │   ├── serializers.py (8.4 KB)
│   │   ├── services.py (7.5 KB)
│   │   ├── tasks.py (5.2 KB)
│   │   ├── throttles.py (659 B)
│   │   ├── urls.py (1.9 KB)
│   │   └── views.py (18.9 KB)
│   └── __init__.py (0 B)
├── config/
│   ├── settings/
│   │   ├── __init__.py (27 B)
│   │   ├── base.py (18.8 KB)
│   │   ├── development.py (2.0 KB)
│   │   └── production.py (3.7 KB)
│   ├── __init__.py (327 B)
│   ├── asgi.py (942 B)
│   ├── celery.py (1.2 KB)
│   ├── urls.py (2.4 KB)
│   └── wsgi.py (931 B)
├── templates/
├── tests/
│   ├── factories/
│   │   ├── __init__.py (794 B)
│   │   ├── auth.py (2.6 KB)
│   │   └── tabyin.py (3.8 KB)
│   └── __init__.py (0 B)
├── static/
├── media/
├── .coverage (164.0 KB)
├── .dockerignore (2.9 KB)
├── .env (4.0 KB)
├── .env.example (4.0 KB)
├── .gitignore (309 B)
├── celerybeat-schedule (12.0 KB)
├── conftest.py (4.4 KB)
├── db.sqlite3 (5.3 MB)
├── docker-compose.yml (4.5 KB)
├── Dockerfile (4.2 KB)
├── entrypoint.sh (4.2 KB)
├── manage.py (1.0 KB)
├── pyproject.toml (5.9 KB)
├── README.md (4.2 KB)
├── requirements.txt (1.2 KB)
├── requirements-dev.txt (802 B)
├── requirements-lock.txt (2.2 KB)
└── schema.yaml (95.8 KB)
```
