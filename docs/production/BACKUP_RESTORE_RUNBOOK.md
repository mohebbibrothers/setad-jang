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
