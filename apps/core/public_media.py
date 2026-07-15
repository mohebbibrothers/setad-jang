"""
Controlled public-media serving for demo/local deployments.

The real production-grade recommendation for user-uploaded public files is an
object store/CDN or a web-server alias. This view intentionally exists for
isolated HTTP demos and local deployments where touching the host Nginx is not
available or not desired.

It is disabled by default and only serves files below MEDIA_ROOT/public/.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils._os import safe_join
from django.views.decorators.http import require_safe


@require_safe
def serve_public_media(request, path: str) -> FileResponse:
    """
    Serve a file from MEDIA_ROOT/public/ when SERVE_PUBLIC_MEDIA=True.

    Security properties:
    - serves public media only; private media is not reachable through this view
    - prevents path traversal with safe_join and resolved-path containment
    - serves files only; no directory listing
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    public_root = (media_root / "public").resolve()

    try:
        candidate = Path(safe_join(public_root, path)).resolve()
    except (ValueError, OSError):
        raise Http404("Public media not found")

    try:
        candidate.relative_to(public_root)
    except ValueError:
        raise Http404("Public media not found")

    if not candidate.is_file():
        raise Http404("Public media not found")

    content_type, encoding = mimetypes.guess_type(str(candidate))
    response = FileResponse(
        candidate.open("rb"),
        content_type=content_type or "application/octet-stream",
    )

    if encoding:
        response["Content-Encoding"] = encoding

    response["Cache-Control"] = "public, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
