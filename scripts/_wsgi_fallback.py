"""Stdlib-only WSGI server for hosts without gunicorn.

Why: some shared hosts cannot reach PyPI, so `pip install gunicorn` fails. This
module serves the Django WSGI application using only the Python standard library
(``wsgiref``) with a threading mix-in so a slow request cannot block the whole
site. It is intentionally minimal - the PHP proxy in the docroot handles HTTP
concerns (headers, gzip, static files) and forwards to this loopback port.

Start it through ``scripts/serve_gunicorn.sh`` (it picks this file automatically
when gunicorn is unavailable); running it directly is also fine for debugging.
"""

from __future__ import annotations

import os
import socketserver
import sys
import wsgiref.simple_server

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")


class ThreadingWSGIServer(socketserver.ThreadingMixIn, wsgiref.simple_server.WSGIServer):
    """Thread-per-request WSGI server (wsgiref's default is single-threaded)."""

    daemon_threads = True
    allow_reuse_address = True


class QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    """Log one line per request without the noisy default format."""

    def log_message(self, format: str, *args: object) -> None:
        """Standard-library hook signature (arg name is part of the API)."""
        sys.stderr.write(f"{self.address_string()} - {format % args}\n")


def main() -> int:
    """Build the WSGI app and block forever serving requests."""
    import django
    from django.core.wsgi import get_wsgi_application

    django.setup()
    application = get_wsgi_application()

    with ThreadingWSGIServer((HOST, PORT), QuietHandler) as httpd:
        httpd.set_app(application)
        sys.stderr.write(f"[wsgi-fallback] listening on {HOST}:{PORT}\n")
        sys.stderr.flush()
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
