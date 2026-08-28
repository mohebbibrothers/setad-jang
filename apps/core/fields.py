"""Custom model fields with security behaviour baked in.

چرا فیلد مدل و نه validator یا سریالایزر: validator فقط می‌تواند «قبول» یا
«رد» کند و اجازهٔ *تغییر* محتوا را ندارد؛ سریالایزر هم فقط یک مسیر ورودی
است و پنل ادمین، فرمان‌های مدیریتی، ایمپورت داده و تست‌ها از کنارش رد
می‌شوند. با قرار دادن پاک‌سازی در ``pre_save`` فیلد، هیچ مسیری در پروژه
نمی‌تواند تصویری با متادیتای دست‌نخورده روی storage بنویسد.
"""

from __future__ import annotations

from django.db import models

from apps.core.file_security import strip_image_metadata


class SanitizedImageField(models.ImageField):
    """An ``ImageField`` that strips EXIF/metadata before writing to storage.

    مسئلهٔ اصلی، مختصات GPS داخل EXIF عکس‌های موبایل است. در اپ R4J که
    کاربران عکس مدرک آپلود می‌کنند، این یعنی موقعیت مکانی گزارش‌دهنده در
    فایلی که بعداً قابل دانلود است باقی می‌ماند.

    اگر پاک‌سازی ممکن نباشد (فرمت ناشناخته، GIF متحرک، فایل خراب) فایل
    اصلی بدون تغییر ذخیره می‌شود. این فیلد هیچ‌وقت نباید باعث شکست یک
    آپلود معتبر شود؛ اعتبارسنجی بر عهدهٔ validatorهاست.
    """

    def pre_save(self, model_instance, add):
        """Sanitize the incoming file, then defer to the normal save flow."""
        file = getattr(model_instance, self.attname)

        # فقط فایل‌هایی که در همین ذخیره‌سازی تازه آپلود شده‌اند. یک فایلی
        # که قبلاً روی storage نشسته دوباره encode نمی‌شود — هم بی‌فایده
        # است و هم هر بار ذخیره، کیفیت JPEG را یک پله پایین می‌آورد.
        if file and not file._committed:
            sanitized = strip_image_metadata(file)
            if sanitized is not None:
                original_name = file.name
                file.file = sanitized
                file.name = original_name

        return super().pre_save(model_instance, add)
