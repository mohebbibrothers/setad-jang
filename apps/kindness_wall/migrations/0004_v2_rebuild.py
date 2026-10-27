"""بازسازی کامل دیوار مهربانی — نسخهٔ ۲ (تختهٔ نیازِ ادمین‌محور).

سیاست اپ از ریشه عوض شد: بازار دوطرفه (کاربر-آگهی/تطبیق/ریسک/گزارش) به
تختهٔ یک‌طرفه تبدیل شد که ادمین دسته و نیاز را می‌سازد و کاربر فقط می‌بیند و
از راه‌های تماس همان آگهی تماس می‌گیرد. dbarِ v1 هیچ ارزش قابل‌انتقالی به v2
نداشت (مدل داده متفاوت است)، پس این مهاجرت آگاهانه DROP می‌کند و از نو
می‌سازد؛ برای همین در عملیاتِ اول، جدولِ قدیمی با تمام داده‌اش حذف می‌شود.

⚠ نکتهٔ استقرار روی پروداکشن: این مهاجرت data-destructive است (۱۲ جدول قدیمی
حذف می‌شوند). قبل از اجرا بکاپِ full گرفته شود — در runbook استقرار ذکر شده.

مهاجرت‌های 0001–0003 هرگز حذف/بازنویسی نشدند: دیتابیس پروداکشن آن‌ها را در
django_migrations ثبت کرده و حذف‌شان یعنی «اسکیپِ بی‌صدا»ی نسخهٔ جدید.
"""

# noqa: I001 -- بدنهٔ operations با makemigrations تولید و بعد دستی ترکیب شده است.

import apps.kindness_wall.models
import apps.kindness_wall.validators
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kindness_wall", "0003_search_gin_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(
            name='KindnessRiskSignal',
        ),
        migrations.DeleteModel(
            name='KindnessDuplicateCandidate',
        ),
        migrations.DeleteModel(
            name='KindnessContactReveal',
        ),
        migrations.DeleteModel(
            name='KindnessBookmark',
        ),
        migrations.DeleteModel(
            name='KindnessListingReport',
        ),
        migrations.DeleteModel(
            name='KindnessMatch',
        ),
        migrations.DeleteModel(
            name='KindnessListingTag',
        ),
        migrations.DeleteModel(
            name='KindnessListingImage',
        ),
        migrations.DeleteModel(
            name='KindnessTag',
        ),
        migrations.DeleteModel(
            name='KindnessKeywordAlias',
        ),
        migrations.DeleteModel(
            name='KindnessListing',
        ),
        migrations.DeleteModel(
            name='KindnessCategory',
        ),
        migrations.CreateModel(
            name='KindnessCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')),
                ('is_active', models.BooleanField(default=True, verbose_name='فعال')),
                ('title', models.CharField(max_length=160, verbose_name='عنوان دسته')),
                ('slug', models.SlugField(allow_unicode=True, blank=True, max_length=200, unique=True, verbose_name='اسلاگ')),
                ('description', models.TextField(blank=True, verbose_name='توضیح دسته')),
                ('icon', models.CharField(blank=True, help_text='یک ایموجی مثل 🍳 یا 🧥 برای نمایش روی کارت دسته.', max_length=8, verbose_name='آیکون (ایموجی)')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='ترتیب نمایش')),
            ],
            options={
                'verbose_name': 'دسته\u200cبندی دیوار مهربانی',
                'verbose_name_plural': 'دسته\u200cبندی\u200cهای دیوار مهربانی',
                'ordering': ['order', 'title'],
                'indexes': [models.Index(fields=['is_active', 'order'], name='kindness_cat_active_order_idx')],
            },
        ),
        migrations.CreateModel(
            name='KindnessListing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')),
                ('is_active', models.BooleanField(default=True, verbose_name='فعال')),
                ('title', models.CharField(max_length=240, verbose_name='عنوان')),
                ('slug', models.SlugField(allow_unicode=True, blank=True, max_length=300, unique=True, verbose_name='اسلاگ')),
                ('description', models.TextField(help_text='چه چیزی، برای چه منظوری و در چه حد و مقداری لازم است.', verbose_name='شرح نیاز')),
                ('quantity', models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)], verbose_name='تعداد/مقدار')),
                ('unit', models.CharField(blank=True, default='عدد', max_length=20, verbose_name='واحد')),
                ('urgency', models.CharField(choices=[('normal', 'عادی'), ('urgent', 'فوری')], db_index=True, default='normal', max_length=10, verbose_name='فوریت')),
                ('is_featured', models.BooleanField(default=False, verbose_name='ویژه (ثبیت بالای دیوار)')),
                ('status', models.CharField(choices=[('draft', 'پیش\u200cنویس'), ('published', 'جاری روی دیوار'), ('fulfilled', 'برطرف\u200cشده'), ('expired', 'منقضی\u200cشده'), ('archived', 'بایگانی\u200cشده')], db_index=True, default='draft', max_length=10, verbose_name='وضعیت')),
                ('beneficiary_name', models.CharField(blank=True, help_text='می\u200cتواند محرمانه باشد؛ مثل «خانواده\u200cای در شوش».', max_length=120, verbose_name='نام/لقب صاحب نیاز')),
                ('province', models.CharField(blank=True, max_length=60, verbose_name='استان')),
                ('city', models.CharField(blank=True, max_length=60, verbose_name='شهر')),
                ('contact_note', models.CharField(blank=True, help_text='مثلاً: «تماس ۱۰ تا ۲۰»، «پیامکی بهتر است».', max_length=240, verbose_name='یادداشت هماهنگی')),
                ('contact_phone', models.CharField(blank=True, max_length=30, verbose_name='شماره تماس')),
                ('contact_bale', models.CharField(blank=True, max_length=64, verbose_name='آیدی بله')),
                ('contact_eitaa', models.CharField(blank=True, max_length=64, verbose_name='آیدی ایتا')),
                ('contact_telegram', models.CharField(blank=True, max_length=64, verbose_name='آیدی تلگرام')),
                ('contact_rubika', models.CharField(blank=True, max_length=64, verbose_name='آیدی روبیکا')),
                ('contact_instagram', models.CharField(blank=True, max_length=64, verbose_name='آیدی اینستاگرام')),
                ('published_at', models.DateTimeField(blank=True, null=True, verbose_name='منتشر شده در')),
                ('expires_at', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='انقضا')),
                ('fulfilled_at', models.DateTimeField(blank=True, null=True, verbose_name='برطرف\u200cشده در')),
                ('fulfillment_note', models.CharField(blank=True, help_text='یک خط صادقانه برای بایگانی «داستان\u200cهای مهربانی».', max_length=240, verbose_name='روایت برطرف\u200cشدن')),
                ('renew_count', models.PositiveSmallIntegerField(default=0, verbose_name='بار تمدید')),
                ('view_count', models.PositiveIntegerField(default=0, verbose_name='بازدید')),
                ('search_document', models.TextField(blank=True, default='', editable=False)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='listings', to='kindness_wall.kindnesscategory', verbose_name='دسته')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_kindness_listings', to=settings.AUTH_USER_MODEL, verbose_name='ثبت\u200cکننده')),
            ],
            options={
                'verbose_name': 'آگهی دیوار مهربانی',
                'verbose_name_plural': 'آگهی\u200cهای دیوار مهربانی',
                'ordering': ['-is_featured', '-published_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='KindnessListingImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')),
                ('is_active', models.BooleanField(default=True, verbose_name='فعال')),
                ('image', models.ImageField(upload_to=apps.kindness_wall.models.listing_image_upload_path, validators=[apps.kindness_wall.validators.validate_listing_image_extension, apps.kindness_wall.validators.validate_listing_image_size], verbose_name='فایل تصویر')),
                ('alt_text', models.CharField(blank=True, max_length=240, verbose_name='متن جایگزین')),
                ('is_cover', models.BooleanField(default=False, verbose_name='کاور')),
                ('order', models.PositiveSmallIntegerField(default=0, verbose_name='ترتیب')),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='kindness_wall.kindnesslisting', verbose_name='آگهی')),
            ],
            options={
                'verbose_name': 'تصویر آگهی دیوار مهربانی',
                'verbose_name_plural': 'تصاویر آگهی\u200cهای دیوار مهربانی',
                'ordering': ['order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='KindnessOffer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاریخ بروزرسانی')),
                ('is_active', models.BooleanField(default=True, verbose_name='فعال')),
                ('message', models.TextField(blank=True, help_text='اختیاری — مثلاً «یک پتوی نو در منزل دارم».', validators=[django.core.validators.MaxLengthValidator(500)], verbose_name='پیام داوطلب')),
                ('status', models.CharField(choices=[('new', 'جدید'), ('contacted', 'تماس گرفته شد'), ('declined', 'رد شد')], db_index=True, default='new', max_length=10, verbose_name='وضعیت پیگیری')),
                ('admin_note', models.CharField(blank=True, max_length=240, verbose_name='یادداشت ادمین')),
                ('handled_at', models.DateTimeField(blank=True, null=True, verbose_name='بررسی در')),
                ('handled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='handled_kindness_offers', to=settings.AUTH_USER_MODEL, verbose_name='بررسی\u200cشده توسط')),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='kindness_wall.kindnesslisting', verbose_name='آگهی')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='kindness_offers', to=settings.AUTH_USER_MODEL, verbose_name='داوطلب')),
            ],
            options={
                'verbose_name': 'اعلام آمادگی دیوار مهربانی',
                'verbose_name_plural': 'اعلام\u200cهای آمادگی دیوار مهربانی',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='kindnesslisting',
            index=models.Index(fields=['status', '-published_at'], name='kindness_list_status_pub_idx'),
        ),
        migrations.AddIndex(
            model_name='kindnesslisting',
            index=models.Index(fields=['category', 'status'], name='kindness_list_cat_status_idx'),
        ),
        migrations.AddIndex(
            model_name='kindnesslisting',
            index=models.Index(fields=['urgency', 'status'], name='kindness_list_urg_st_idx'),
        ),
        migrations.AddIndex(
            model_name='kindnesslisting',
            index=models.Index(fields=['city', 'status'], name='kindness_list_city_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='kindnesslisting',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gte', 1)), name='kindness_listing_quantity_positive'),
        ),
        migrations.AddIndex(
            model_name='kindnesslistingimage',
            index=models.Index(fields=['listing', 'is_cover', 'order'], name='kindness_img_cover_idx'),
        ),
        migrations.AddIndex(
            model_name='kindnessoffer',
            index=models.Index(fields=['status', '-created_at'], name='kindness_offer_status_idx'),
        ),
        migrations.AddIndex(
            model_name='kindnessoffer',
            index=models.Index(fields=['listing', 'status'], name='kindness_offer_listing_idx'),
        ),
        migrations.AddConstraint(
            model_name='kindnessoffer',
            constraint=models.UniqueConstraint(fields=('listing', 'user'), name='uniq_kindness_offer_per_user'),
        ),
    ]
