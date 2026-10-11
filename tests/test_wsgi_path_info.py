"""تست‌های چارچوبِ اصلاحِ PATH_INFO در config.wsgi (قرارداد PEP 3333).

انگیزه: Passenger روی هاست اشتراکیِ cPanel مسیر را percent-decode نمی‌کند؛
هر اسلاگِ فارسی یا نامِ فایلِ غیرASCII بدون این لایه ۴۰۴ می‌شود — این
چارچوب باید فقط در همان سناریو وارد عمل شود و روی سرورهای درست‌رفتار
(gunicorn، dev server) کاملاً شفاف (idempotent) باشد.
"""

from urllib.parse import quote

from config.wsgi import application, fix_wsgi_path_info


def test_encoded_persian_path_is_normalized_to_pep3333():
    slug = "چریک-سایبری-cherik-cyber"
    environ = {"PATH_INFO": f"/api/v1/lms/courses/{quote(slug, safe='')}/"}
    fixed = fix_wsgi_path_info(environ)
    expected = f"/api/v1/lms/courses/{slug}/".encode().decode("latin-1")
    assert fixed["PATH_INFO"] == expected
    # environ ورودی نباید in-place تغییر کرده باشد
    assert environ["PATH_INFO"] != expected


def test_decoded_persian_path_passes_through_untouched():
    # سرور درست‌رفتار: رشته‌ی latin-1ِ بایت‌های دیکدشده (بدون «%»)
    environ = {"PATH_INFO": "/x/ÚØ±/y/"}
    assert fix_wsgi_path_info(environ) is environ


def test_plain_ascii_path_untouched():
    environ = {"PATH_INFO": "/api/v1/lms/courses/"}
    assert fix_wsgi_path_info(environ) is environ


def test_percent_with_invalid_utf8_sequence_is_left_alone():
    # توکنِ %ff%fe هگز معتبر دارد اما UTF-8 نمی‌سازد → شفاف عبور کند
    environ = {"PATH_INFO": "/files/report%ff%fe.txt"}
    assert fix_wsgi_path_info(environ) is environ


def test_application_applies_fix_before_handoff(monkeypatch):
    captured: dict = {}

    def fake_django(environ, start_response):
        captured.update(environ)
        start_response("200 OK", [])
        return [b"ok"]

    monkeypatch.setattr("config.wsgi._django_application", fake_django)
    slug = "چریک-سایبری"
    env = {"PATH_INFO": f"/x/{quote(slug, safe='')}/"}
    body = b"".join(application(env, lambda *args: None))
    assert body == b"ok"
    assert captured["PATH_INFO"] == f"/x/{slug}/".encode().decode("latin-1")
