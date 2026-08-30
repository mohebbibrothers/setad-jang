# Backup and Restore Runbook

## 1. What must be backed up

```text
PostgreSQL database
Object storage bucket / media files
.env / secrets in secret manager
schema.yaml and deployed git SHA
```

## 2. PostgreSQL backup

Logical backup:

```bash
pg_dump --format=custom --no-owner --no-acl \
  --dbname="$DATABASE_URL" \
  --file="backup-setadjang-$(date +%Y%m%d-%H%M%S).dump"
```

Docker/local compose example:

```bash
docker-compose exec postgres pg_dump -U setadjang -d setadjang --format=custom --no-owner --no-acl > backup.dump
```

## 3. PostgreSQL restore

```bash
createdb setadjang_restore
pg_restore --clean --if-exists --no-owner --no-acl \
  --dbname=setadjang_restore \
  backup.dump
```

Docker/local compose example:

```bash
cat backup.dump | docker-compose exec -T postgres pg_restore -U setadjang -d setadjang --clean --if-exists --no-owner --no-acl
```

## 4. Media/Object storage backup

For S3-compatible storage:

```bash
aws s3 sync s3://setadjang-media ./media-backup --delete
```

For MinIO:

```bash
mc mirror --overwrite minio/setadjang-media ./media-backup
```

## 5. Restore validation

After restore:

```bash
python manage.py migrate --check
python manage.py check
python manage.py spectacular --validate --file /tmp/schema.yaml
```

Then smoke:

```text
login
public reports
madadkar payment history
lms certificate verification
kindness contact reveal audit
support ticket history
```

## 6. Backup policy

Recommended minimum:

```text
daily database backup
weekly full media backup
30-day retention
monthly restore drill
backup encryption at rest
access audit on backup storage
```

## 7. Automated backup service (added in phase 8 — P2-11)

از این فاز، بکاپ دیگر «یادآوریِ انسانی» نیست؛ سرویس `backup` در
`docker-compose.yml` (ایمیج `postgres:17-alpine` — نسخهٔ pg_dump قفل با سرور)
روی volume مشترک `backup_data` به مسیر `/backups` می‌نویسد:

```text
/backups/dumps/setadjang-<UTC timestamp>.dump        # pg_dump -Fc، -Z6، no-owner/acl
/backups/dumps/setadjang-<...>.dump.sha256           # checksum هر فایل
/backups/wal/<walfile>                               # آرشیو WAL (archive_timeout=300 → RPO≤۵دقیقه)
/backups/.backup_ok / .verify_ok / .backup_failed    # پرچم‌های سلامت برای healthcheck/مانیتورینگ
```

سیاست (override با env — بخش «سرویس بکاپ» در `.env.example`):
interval ۶ ساعت، retention دامپ ۱۴ روز، retention WAL ۷ روز، و هر ۴ بکاپ یک
**آزمونِ بازگردانی واقعی**: dump در DB موقت `setadjang_verify_*` با
`--exit-on-error` restore می‌شود، شمارش `django_migrations` و جداول public
سنجیده می‌شوند، بعد drop. بکاپی که restoreنشده، بکاپ نیست.

### 7.1 دستی/فوری

```bash
# بکاپ فوری (بدون صبر برای تایمر):
docker compose exec backup sh -c 'cd /backups/dumps && pg_dump --format=custom --no-owner --no-acl -f "manual-$(date -u +%Y%m%d-%H%M%S).dump"'
# آزمون بازگردانی روی آخرین dump:
docker compose run --rm --no-deps backup sh /backup/verify_restore.sh
```

### 7.2 بازگردانی نقطه‌ای (PITR) تا پنجرۀ WAL

```bash
# در maintenance window؛ روی cluster تازه (نه همان DB زنده):
pg_restore ... /backups/dumps/<dump>.dump      # تا زمانِ dump
# و برای دقیقه‌های بعد از dump، replay تا هدفِ زمانی:
recovery_target_time = '...'                   # با pg_rewind/restore_command روی /backups/wal
```

### 7.3 محدودیت صادقانه و offsite

`backup_data` **روی همان هاست** است: دربرابر حذف/فاسدشدگی منطقی و خطای
اپراتور محافظت می‌کند، نه مرگِ دیسک/سرور. حداقل روزی یک‌بار با rclone/restic
از `/var/lib/docker/volumes/setadjang_backup_data/_data` (یا exportِ volume)
به مقصدِ خارج از هاست همگام‌سازی شود؛ رمزنگاری در مقصد الزامی است (dump
شامل دادهٔ مالی/کیفی است). این کار، سیاستِ §6 (۳۰ روز retention، drill ماهانه)
تأییدشدهٔ قبلی را نقض نمی‌کند — مکمل خودکارسازی‌اش است.

### 7.4 مانیتورینگ

healthcheck سرویس (سنِ `.backup_ok` < ۳×interval) + `/api/v1/metrics/` برای
downtime؛ اگر `.backup_failed` ظاهر شد: incident است، نه warning — لاگ سرویس
و §2 همین runbook را ببین.
