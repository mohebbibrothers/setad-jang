#!/usr/bin/env python
# ============================================================================
#  auth_doctor.py - why does a successful login die on the very next request?
#
#  SYMPTOM THIS EXPLAINS
#  ---------------------
#      «کاربر لاگین می‌کند و همان لحظه از حسابش بیرون انداخته می‌شود.»
#
#  The project binds every JWT to a server-side AuthSession row through a `sid`
#  claim (SessionAwareJWTAuthentication). A session that is missing, revoked or
#  bound to a rotated refresh token turns the *next* request into a 401, and the
#  frontend reacts to a 401 by clearing the tokens - i.e. an instant logout.
#  There are only a handful of ways that can happen, and this script tests each
#  of them **in process** (no network, no browser, no password needed):
#
#      1  configuration census (JWT lifetimes, rotation, blacklist, cache,
#         NUM_PROXIES, ALLOWED_HOSTS, CSRF/CORS)
#      2  session census (how many rows, revoked ratio, expired-but-active,
#         timestamps in the future => a clock that moved during the migration)
#      3  live round trip   : issue a real login session -> GET /auth/me/
#      4  refresh           : rotate -> GET /auth/me/ with the new access
#      5  refresh RACE      : reuse the previous refresh token (what two parallel
#                             loaders or a double-mounted effect do) -> this is
#                             the classic cause of "logged in, instantly out"
#      6  revocation        : revoke the session -> next request must be 401
#
#  USAGE (from the app root)
#      <venv>/python scripts/auth_doctor.py
#      <venv>/python scripts/auth_doctor.py --identifier 09121234567
#      <venv>/python scripts/auth_doctor.py --identifier 09121234567 --json /tmp/auth.json
#
#  SAFETY
#      - read-only unless --identifier is given
#      - the test session/tokens it creates are deleted again at the end
#      - no password, no OTP, nothing is printed that could be replayed
# ============================================================================
"""Auth/session doctor: configuration census + in-process login simulation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = "config.settings.production"
ME_PATH = "/api/v1/auth/me/"
REFRESH_PATH = "/api/v1/auth/token/refresh/"
HOST = "api.besat.me"


# --------------------------------------------------------------------------- boot
def project_root() -> str:
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "manage.py").exists():
            return str(candidate)
    return str(Path.cwd())


def boot_django(settings: str) -> None:
    root = project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings)
    import django

    django.setup()


def say(title: str) -> None:
    print(f"\n=== {title}", file=sys.stderr)


def info(text: str) -> None:
    print(f"       {text}", file=sys.stderr)


def ok(text: str) -> None:
    print(f"  [OK] {text}", file=sys.stderr)


def warn(text: str) -> None:
    print(f"  [--] {text}", file=sys.stderr)


def bad(text: str) -> None:
    print(f"  [!!] {text}", file=sys.stderr)


# ------------------------------------------------------------------ 1 config
def config_census() -> dict[str, Any]:
    from django.conf import settings

    say("1/6 configuration")
    jwt = getattr(settings, "SIMPLE_JWT", {}) or {}
    data: dict[str, Any] = {
        "AUTH_USER_MODEL": getattr(settings, "AUTH_USER_MODEL", ""),
        "DEBUG": bool(settings.DEBUG),
        "CACHE_BACKEND": (settings.CACHES.get("default", {}) or {}).get("BACKEND", ""),
        "NUM_PROXIES": getattr(settings, "NUM_PROXIES", None),
        "ALLOWED_HOSTS": list(getattr(settings, "ALLOWED_HOSTS", []) or []),
        "CSRF_TRUSTED_ORIGINS": list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []),
        "CORS_ALLOW_ALL_ORIGINS": getattr(settings, "CORS_ALLOW_ALL_ORIGINS", None),
        "SESSION_COOKIE_SECURE": getattr(settings, "SESSION_COOKIE_SECURE", None),
        "SESSION_COOKIE_SAMESITE": getattr(settings, "SESSION_COOKIE_SAMESITE", None),
        "CSRF_COOKIE_SECURE": getattr(settings, "CSRF_COOKIE_SECURE", None),
        "AUTHENTICATION_CLASSES": list(
            (settings.REST_FRAMEWORK.get("DEFAULT_AUTHENTICATION_CLASSES", []) or [])
            if hasattr(settings, "REST_FRAMEWORK")
            else []
        ),
        "JWT": {
            "ACCESS_TOKEN_LIFETIME": str(jwt.get("ACCESS_TOKEN_LIFETIME", "")),
            "REFRESH_TOKEN_LIFETIME": str(jwt.get("REFRESH_TOKEN_LIFETIME", "")),
            "ROTATE_REFRESH_TOKENS": jwt.get("ROTATE_REFRESH_TOKENS"),
            "BLACKLIST_AFTER_ROTATION": jwt.get("BLACKLIST_AFTER_ROTATION"),
            "AUTH_HEADER_TYPES": list(jwt.get("AUTH_HEADER_TYPES", ())),
        },
    }
    info(f"AUTH_USER_MODEL      : {data['AUTH_USER_MODEL']}")
    info(f"CACHE backend        : {data['CACHE_BACKEND']}")
    info(f"NUM_PROXIES          : {data['NUM_PROXIES']}")
    info(f"ALLOWED_HOSTS        : {', '.join(data['ALLOWED_HOSTS']) or '(empty)'}")
    info(f"CSRF_TRUSTED_ORIGINS : {', '.join(data['CSRF_TRUSTED_ORIGINS']) or '(empty)'}")
    info(f"CORS allow all       : {data['CORS_ALLOW_ALL_ORIGINS']}")
    info(
        f"access/refresh       : {data['JWT']['ACCESS_TOKEN_LIFETIME']} / {data['JWT']['REFRESH_TOKEN_LIFETIME']}"
    )
    info(
        f"rotate / blacklist   : {data['JWT']['ROTATE_REFRESH_TOKENS']} / {data['JWT']['BLACKLIST_AFTER_ROTATION']}"
    )
    for cls in data["AUTHENTICATION_CLASSES"]:
        info(f"auth class           : {cls}")

    if "locmem" in str(data["CACHE_BACKEND"]):
        warn("cache is per-process (locmem): revocation is invisible to other workers until TTL")
    else:
        ok(f"shared cache backend: {data['CACHE_BACKEND']}")
    if not data["CSRF_TRUSTED_ORIGINS"]:
        warn("CSRF_TRUSTED_ORIGINS is empty (Django 4+ requires https://besat.me for admin forms)")
    return data


# ----------------------------------------------------------------- 2 sessions
def session_census() -> dict[str, Any]:
    from datetime import timedelta

    from django.utils import timezone

    from apps.authentication.models import AuthSession

    say("2/6 session registry")
    now = timezone.now()
    total = AuthSession.objects.count()
    revoked = AuthSession.objects.filter(is_revoked=True).count()
    active = total - revoked
    expired_active = AuthSession.objects.filter(
        is_revoked=False, expires_at__isnull=False, expires_at__lt=now
    ).count()
    future_seen = AuthSession.objects.filter(last_seen_at__gt=now + timedelta(minutes=5)).count()
    future_created = AuthSession.objects.filter(created_at__gt=now + timedelta(minutes=5)).count()
    recent_1h = AuthSession.objects.filter(created_at__gte=now - timedelta(hours=1)).count()

    ok(
        f"rows: {total} total, {active} active, {revoked} revoked, {recent_1h} created in the last hour"
    )
    if total and revoked / total > 0.9 and total > 20:
        warn(f"{revoked}/{total} sessions revoked - something is revoking aggressively")
    if expired_active:
        bad(
            f"{expired_active} session(s) are NOT revoked but already past expires_at (auth will 401)"
        )
    if future_seen or future_created:
        bad(
            f"clock anomaly: {future_created} created_at / {future_seen} last_seen_at in the FUTURE "
            "=> the server clock moved (Java-style token/session expiry breaks immediately)"
        )
    elif total:
        ok("no timestamps in the future (server clock looks sane)")

    rows = []
    for s in AuthSession.objects.order_by("-created_at")[:10]:
        rows.append(
            {
                "id": s.pk,
                "user": s.user_id,
                "revoked": s.is_revoked,
                "device": s.device_label,
                "ip": str(s.ip_address or "-"),
                "created": s.created_at.isoformat(timespec="seconds"),
                "last_seen": s.last_seen_at.isoformat(timespec="seconds"),
                "expires": s.expires_at.isoformat(timespec="seconds") if s.expires_at else None,
            }
        )
    if rows:
        info("last 10 sessions:")
        for r in rows:
            state = "REVOKED" if r["revoked"] else "active "
            print(
                f"         #{r['id']:<6} user={r['user']:<5} {state} {r['created']} "
                f"seen={r['last_seen']} exp={r['expires']} {r['device']}",
                file=sys.stderr,
            )
    return {
        "total": total,
        "active": active,
        "revoked": revoked,
        "expired_active": expired_active,
        "future_seen": future_seen,
        "future_created": future_created,
        "recent": rows,
    }


# --------------------------------------------------------- 3-6 live simulation
def _marker_ids() -> dict[str, int]:
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    from apps.authentication.models import AuthSession

    def max_id(model: Any) -> int:
        last = model.objects.order_by("-id").values_list("id", flat=True).first()
        return int(last or 0)

    return {
        "session": max_id(AuthSession),
        "outstanding": max_id(OutstandingToken),
        "blacklisted": max_id(BlacklistedToken),
    }


def _cleanup(markers: dict[str, int]) -> None:
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    from apps.authentication.models import AuthSession

    AuthSession.objects.filter(id__gt=markers["session"]).delete()
    BlacklistedToken.objects.filter(id__gt=markers["blacklisted"]).delete()
    OutstandingToken.objects.filter(id__gt=markers["outstanding"]).delete()


def _client():
    from django.test import Client

    return Client(SERVER_NAME=HOST, HTTP_HOST=HOST)


def live_simulation(identifier: str) -> dict[str, Any]:
    from django.contrib.auth import get_user_model

    from apps.authentication.services import _build_login_result

    say("3/6 live round trip (in process, no network)")
    User = get_user_model()
    user = None
    candidate = identifier.strip()
    lookups = [{"username": candidate}, {"phone_number": candidate}, {"email": candidate}]
    for lookup in lookups:
        try:
            user = User.objects.filter(**lookup).first()
        except Exception:  # field may not exist on a custom model
            user = None
        if user:
            break
    if user is None:
        bad(f"no user matched {identifier!r} (tried username / phone_number / email)")
        return {"found": False}

    ok(f"user #{user.pk} ({user.username}) is_active={user.is_active}")
    if not user.is_active:
        bad("user is inactive - every authenticated request will be rejected")

    markers = _marker_ids()
    result: dict[str, Any] = {"found": True, "user": user.pk}
    try:
        request = _client().request().wsgi_request
        request.META["HTTP_USER_AGENT"] = "besat-auth-doctor/1.0"
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        login = _build_login_result(user=user, request=request)
        access = login["tokens"]["access"]
        refresh = login["tokens"]["refresh"]
        session = login["session"]
        ok(f"session #{session.pk} created (expires {session.expires_at})")

        client = _client()
        r = client.get(ME_PATH, HTTP_AUTHORIZATION=f"Bearer {access}")
        result["me_after_login"] = r.status_code
        if r.status_code == 200:
            ok(f"GET {ME_PATH} -> 200 (token + session are consistent)")
        else:
            bad(f"GET {ME_PATH} -> {r.status_code}: {r.content[:200]!r}")

        say("4/6 refresh (rotation)")
        r2 = client.post(
            REFRESH_PATH,
            data=json.dumps({"refresh": refresh}),
            content_type="application/json",
        )
        result["refresh"] = r2.status_code
        new_refresh = ""
        new_access = ""
        if r2.status_code == 200:
            payload = r2.json()
            body = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            new_refresh = str(body.get("refresh", ""))
            new_access = str(body.get("access", ""))
            ok(f"POST {REFRESH_PATH} -> 200 (new access issued, rotated={bool(new_refresh)})")
            r3 = client.get(ME_PATH, HTTP_AUTHORIZATION=f"Bearer {new_access}")
            result["me_after_refresh"] = r3.status_code
            if r3.status_code == 200:
                ok(f"GET {ME_PATH} with the NEW access -> 200")
            else:
                bad(f"GET {ME_PATH} with the NEW access -> {r3.status_code}")
        else:
            bad(f"POST {REFRESH_PATH} -> {r2.status_code}: {r2.content[:200]!r}")

        say("5/6 refresh race (two parallel loaders using the same refresh token)")
        r4 = client.post(
            REFRESH_PATH,
            data=json.dumps({"refresh": refresh}),
            content_type="application/json",
        )
        result["refresh_reuse"] = r4.status_code
        if r4.status_code == 200:
            ok("reusing the old refresh token still works (no instant-logout risk)")
        else:
            warn(
                f"reusing the old refresh token -> {r4.status_code}. This is EXPECTED with "
                "BLACKLIST_AFTER_ROTATION; the frontend must never refresh twice in parallel "
                "(single-flight is already implemented in src/lib/auth-tokens.ts - verify it)."
            )

        say("6/6 revocation")
        from django.utils import timezone as tz

        session.is_revoked = True
        session.revoked_at = tz.now()
        session.save(update_fields=["is_revoked", "revoked_at"])
        r5 = client.get(ME_PATH, HTTP_AUTHORIZATION=f"Bearer {access}")
        result["me_after_revoke"] = r5.status_code
        if r5.status_code == 401:
            ok("after revoking the session the next request is 401 (binding works)")
        else:
            bad(f"after revoking the session the request is {r5.status_code} (expected 401)")
    finally:
        _cleanup(markers)
        info("test session and tokens removed")
    return result


# ----------------------------------------------------------------------- main
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="auth/session doctor")
    parser.add_argument(
        "--settings", default=os.environ.get("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS)
    )
    parser.add_argument("--identifier", default="", help="username / phone / email to simulate")
    parser.add_argument("--json", help="write the report as JSON")
    args = parser.parse_args(argv)

    boot_django(args.settings)
    report: dict[str, Any] = {}
    report["config"] = config_census()
    report["sessions"] = session_census()
    if args.identifier:
        report["live"] = live_simulation(args.identifier)
    else:
        say("3-6/6 live simulation")
        info("skipped - pass --identifier 09121234567 to simulate a real login")

    print("", file=sys.stderr)
    print("============================================================", file=sys.stderr)
    problems = 0
    sess = report["sessions"]
    if sess["expired_active"] or sess["future_seen"] or sess["future_created"]:
        problems += 1
    live = report.get("live") or {}
    for key in ("me_after_login", "refresh", "me_after_refresh", "me_after_revoke"):
        if key in live and live[key] not in (200, 401):
            problems += 1
    if live.get("me_after_login") not in (None, 200):
        problems += 1
    print(f" RESULT: {problems} blocking problem(s) found", file=sys.stderr)
    print("============================================================", file=sys.stderr)

    if args.json:
        Path(args.json).expanduser().write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        info(f"json report: {args.json}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
