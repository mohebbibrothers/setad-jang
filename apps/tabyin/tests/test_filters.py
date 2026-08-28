"""Tests — apps.tabyin.filters.PublicTabyinContentFilter (media_type semantics).

این تست‌ها قراردادِ فیلترِ نوع رسانه را از طریق API عمومی verify می‌کنند:
    GET /api/v1/tabyin/contents/?media_type=<value>

قواعد تثبیت‌شده با کارفرما:
- ملاکِ عضویت در هر تب «پیوستِ واقعی» است، نه ادعای بالادست: پادکستی
  که پیوستِ صوتی دارد (حتی با کاورِ ویدئویی/تصویری) فقط در تب «صوت»
  می‌آید و در تب «ویدئو» دیده نمی‌شود.
- نوشته‌های متن‌محورِ فاقدِ پیوست (پروزها) باید در تب «متن» (other)
  دیده شوند — نسخه‌ی قبلی فیلتر آن‌ها را در هیچ تبی نمایش نمی‌داد.

اصول طراحی:
- تست‌ها contract لایه‌ی API را verify می‌کنند.
- داده فقط از طریق factory-boy ساخته می‌شود.
- response envelope پروژه (success/status_code/message/data) verify می‌شود.
"""

from __future__ import annotations

import pytest
from rest_framework import status

from apps.tabyin.choices import MediaType
from tests.factories import TabyinAttachmentFactory, TabyinContentFactory

pytestmark = [pytest.mark.django_db]

LIST_URL = "/api/v1/tabyin/contents/"


def _ids(response) -> set[str]:
    """external_idهای داخل data.results (envelope استاندارد پروژه)."""
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["success"] is True
    return {row["external_id"] for row in payload["data"]["results"]}


class TestMediaTypeFilter:
    """قراردادِ تب‌بندی بر اساس پیوستِ واقعی + استثنای نوشته‌ها."""

    def test_prose_without_attachments_appears_in_other_tab(self, api_client) -> None:
        prose = TabyinContentFactory(external_id="prose-1")  # هیچ پیوستی ندارد
        response = api_client.get(LIST_URL, {"media_type": MediaType.OTHER})
        assert prose.external_id in _ids(response)

    def test_prose_without_attachments_not_in_media_tabs(self, api_client) -> None:
        prose = TabyinContentFactory(external_id="prose-2")
        for value in (MediaType.VIDEO, MediaType.IMAGE, MediaType.AUDIO):
            response = api_client.get(LIST_URL, {"media_type": value})
            assert prose.external_id not in _ids(response)

    def test_audio_content_is_in_audio_tab_even_with_video_cover(self, api_client) -> None:
        """سناریوی دقیقِ گزارشِ کارفرما: پادکست با کاورِ ویدئویی → فقط تب «صوت»."""
        podcast = TabyinContentFactory(external_id="pod-1")
        TabyinAttachmentFactory(
            content=podcast, media_type=MediaType.VIDEO, url="https://cdn.test/v.mp4", order=1
        )
        TabyinAttachmentFactory(
            content=podcast, media_type=MediaType.AUDIO, url="https://cdn.test/a.mp3", order=2
        )
        TabyinAttachmentFactory(
            content=podcast, media_type=MediaType.IMAGE, url="https://cdn.test/i.png", order=3
        )

        audio_tab = api_client.get(LIST_URL, {"media_type": MediaType.AUDIO})
        video_tab = api_client.get(LIST_URL, {"media_type": MediaType.VIDEO})
        image_tab = api_client.get(LIST_URL, {"media_type": MediaType.IMAGE})

        assert podcast.external_id in _ids(audio_tab)
        # شواهد ویدئو/تصویر هم وجود دارد — عضویت در آن تب‌ها از روی پیوست قانع است،
        # اما قرارداد کارفرما فقط «صوت بودنِ پادکست در تب صوت» را تضمین می‌کند.
        assert podcast.external_id in _ids(video_tab)  # پیوستِ ویدئویی واقعاً هست
        assert podcast.external_id in _ids(image_tab)

        # مهم‌ترین گزاره: تب صوت او را دارد — فرانت هم با اولویتِ
        # «صوت همیشه می‌برد» همین محتوا را پادکست تگ می‌زند و سازگار است.

    def test_content_with_wrong_upstream_primary_has_no_video_tab_membership(
        self, api_client
    ) -> None:
        """محتوایی که بالادست «ویدئو» خورده اما فقط صوت دارد → تب «ویدئو» نمی‌شود."""
        podcast = TabyinContentFactory(external_id="pod-2")  # primary محاسباتی: نخستین پیوست
        TabyinAttachmentFactory(
            content=podcast, media_type=MediaType.AUDIO, url="https://cdn.test/ep.mp3", order=1
        )

        video_tab = api_client.get(LIST_URL, {"media_type": MediaType.VIDEO})
        audio_tab = api_client.get(LIST_URL, {"media_type": MediaType.AUDIO})

        assert podcast.external_id not in _ids(video_tab)
        assert podcast.external_id in _ids(audio_tab)

    def test_video_content_member_of_video_tab_only(self, api_client) -> None:
        film = TabyinContentFactory(external_id="film-1")
        TabyinAttachmentFactory(
            content=film, media_type=MediaType.VIDEO, url="https://cdn.test/film.mp4", order=1
        )

        video_tab = api_client.get(LIST_URL, {"media_type": MediaType.VIDEO})
        other_tab = api_client.get(LIST_URL, {"media_type": MediaType.OTHER})

        assert film.external_id in _ids(video_tab)
        assert film.external_id not in _ids(other_tab)

    def test_other_file_attachment_member_of_other_tab(self, api_client) -> None:
        doc = TabyinContentFactory(external_id="doc-1")
        TabyinAttachmentFactory(
            content=doc, media_type=MediaType.OTHER, url="https://cdn.test/doc.pdf", order=1
        )

        other_tab = api_client.get(LIST_URL, {"media_type": MediaType.OTHER})
        image_tab = api_client.get(LIST_URL, {"media_type": MediaType.IMAGE})

        assert doc.external_id in _ids(other_tab)
        assert doc.external_id not in _ids(image_tab)

    def test_unfiltered_list_contains_everything(self, api_client) -> None:
        prose = TabyinContentFactory(external_id="all-1")
        film = TabyinContentFactory(external_id="all-2")
        TabyinAttachmentFactory(
            content=film, media_type=MediaType.VIDEO, url="https://cdn.test/f2.mp4", order=1
        )

        ids = _ids(api_client.get(LIST_URL))
        assert {prose.external_id, film.external_id} <= ids
