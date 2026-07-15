from __future__ import annotations

from pathlib import Path

import pytest
from django.http import FileResponse, Http404
from django.test import RequestFactory, override_settings

from apps.core.public_media import serve_public_media


@pytest.mark.django_db
def test_serve_public_media_serves_file_under_public_root(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    file_path = media_root / "public" / "r4j" / "photo.png"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"\x89PNG\r\n\x1a\ncontent")

    request = RequestFactory().get("/media/public/r4j/photo.png")

    with override_settings(MEDIA_ROOT=media_root):
        response = serve_public_media(request, "r4j/photo.png")

    try:
        assert isinstance(response, FileResponse)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert response["Cache-Control"] == "public, max-age=3600"
    finally:
        response.close()


@pytest.mark.django_db
def test_serve_public_media_rejects_path_traversal(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    secret = media_root / "private" / "secret.txt"
    secret.parent.mkdir(parents=True)
    secret.write_text("secret")

    request = RequestFactory().get("/media/public/../private/secret.txt")

    with override_settings(MEDIA_ROOT=media_root), pytest.raises(Http404):
        serve_public_media(request, "../private/secret.txt")


@pytest.mark.django_db
def test_serve_public_media_does_not_list_directories(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    public_dir = media_root / "public" / "r4j"
    public_dir.mkdir(parents=True)

    request = RequestFactory().get("/media/public/r4j/")

    with override_settings(MEDIA_ROOT=media_root), pytest.raises(Http404):
        serve_public_media(request, "r4j")
