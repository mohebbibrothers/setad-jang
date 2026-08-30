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

**رفع F1 ممیزی (۲۰۲۶-۰۸-۳۰):** دامپِ منطقی *پایۀ* replay وال نیست؛ لذا چرخه،
هر `BASE_BACKUP_INTERVAL_SECONDS` (پیش‌فرض روزی یک) یک **pg_basebackup فیزیکی**
(`-Ft -z -Xf`) در `/backups/base/setadjang-base-<stamp>/` می‌گیرد:
`base.tar.gz` + `pg_wal.tar.gz` + `backup_manifest` + `SHA256SUMS`، پرچمِ
`.basebackup_ok`، و verify چرخشی هم tar-integrity و manifestِ PG17 را می‌سنجد.
نتیجه: پنجرۀ PITR واقعی = `min(BASE_BACKUP_KEEP_DAYS, BACKUP_WAL_KEEP_DAYS)`
(پیش‌فرض ۷ روز) با RPO≤۵ دقیقه در *بعداز* نخستین basebackup؛ پیش از آن
فقط بازیابیِ نقطه‌ایِ «تا زمانِ آخرین دامپ» در دسترس است.

### 7.1 دستی/فوری

```bash
# بکاپ فوری (بدون صبر برای تایمر):
docker compose exec backup sh -c 'cd /backups/dumps && pg_dump --format=custom --no-owner --no-acl -f "manual-$(date -u +%Y%m%d-%H%M%S).dump"'
# آزمون بازگردانی روی آخرین dump + integrityِ basebackup:
docker compose run --rm --no-deps backup sh /backup/verify_restore.sh
# basebackup فوری (بدون صبر برای سررسید روزانه):
docker compose exec backup sh -c '
  s=$(date -u +%Y%m%dT%H%M%SZ); d=/backups/base/setadjang-base-$s
  mkdir -p $d && pg_basebackup -D $d -Ft -z -Xf -P
  (cd $d && sha256sum base.tar.gz pg_wal.tar.gz > SHA256SUMS) && touch /backups/.basebackup_ok'
```

### 7.2 بازگردانی نقطه‌ای (PITR) — روی پایهٔ فیزیکی، نه دامپ

دو مسیرِ *جدا*، که نباید قاطی شوند:

**الف) بازیابی منطقی (سریع، بدونِ وال):** `pg_restore` دامپِ دلخواه —
رساندن به زمانِ دامپ و نه دقیق‌تر. برای خرابیِ منطقی/اپراتوریِ جدول‌محور.

**ب) PITR واقعی (دقیق تا دقیقه):** فقط با basebackup:

```bash
# maintenance window؛ cluster تازه (نه همان volume زنده):
docker compose stop web worker
docker compose run --rm --no-deps -v setadjang_backup_data:/backups postgres sh -c '
  rm -rf /var/lib/postgresql/data/*
  tar -xzf /backups/base/setadjang-base-<STAMP>/base.tar.gz -C /var/lib/postgresql/data
  mkdir -p /var/lib/postgresql/data/pg_wal/restore && cp /backups/wal/* /var/lib/postgresql/data/pg_wal/restore/ 2>/dev/null || true
  tar -xzf /backups/base/setadjang-base-<STAMP>/pg_wal.tar.gz -C /var/lib/postgresql/data/pg_wal
  echo "restore_command = '''cp /backups/wal/%f %p'''" > /var/lib/postgresql/data/postgresql.auto.conf
  echo "recovery_target_time = '''2026-08-30 14:03:00+00'''" >> /var/lib/postgresql/data/postgresql.auto.conf
  echo "recovery_target_action = '''promote'''" >> /var/lib/postgresql/data/postgresql.auto.conf
  touch /var/lib/postgresql/data/RECOVERY.signal
'
docker compose up -d postgres   # لاگ را ببین: replay → promote
docker compose up -d web worker
```

اگر WALِ لازم پاک شده باشد (خارجِ پنجره)، pg_basebackupِ منطقی‌ترین
fallback همان دامپ است — «دقیق تا دقیقه» را فقط داخلِ پنجره وعده بده.

### 7.3 محدودیت صادقانه و offsite

`backup_data` (دامپ‌ها + `/backups/base` + `/backups/wal`) **روی همان هاست** است: دربرابر حذف/فاسدشدگی منطقی و خطای
اپراتور محافظت می‌کند، نه مرگِ دیسک/سرور. حداقل روزی یک‌بار با rclone/restic
از `/var/lib/docker/volumes/setadjang_backup_data/_data` (یا exportِ volume)
به مقصدِ خارج از هاست همگام‌سازی شود؛ رمزنگاری در مقصد الزامی است (dump
شامل دادهٔ مالی/کیفی است). این کار، سیاستِ §6 (۳۰ روز retention، drill ماهانه)
تأییدشدهٔ قبلی را نقض نمی‌کند — مکمل خودکارسازی‌اش است.

### 7.4 مانیتورینگ

healthcheck سرویس (سنِ `.backup_ok` < ۳×interval) + `/api/v1/metrics/` برای
downtime؛ اگر `.backup_failed` ظاهر شد: incident است، نه warning — لاگ سرویس
و §2 همین runbook را ببین.
