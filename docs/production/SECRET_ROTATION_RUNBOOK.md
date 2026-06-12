# Secret Rotation Runbook

## 1. Secrets to rotate

```text
SECRET_KEY
JWT_SIGNING_KEY
POSTGRES_PASSWORD
REDIS password/URL if managed provider supports it
EMAIL_HOST_PASSWORD / Brevo SMTP key
SMS_API_KEY
MADADKAR_ZARINPAL_MERCHANT_ID if compromised
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
GitHub tokens
Sentry DSN if needed
```

## 2. GitHub token leak response

If a GitHub token was pasted in chat or logs:

1. Revoke token in GitHub immediately.
2. Create a new scoped token only if still needed.
3. Never store token in git remote config.
4. Use temporary askpass files and delete them immediately.
5. Verify:

```bash
git remote -v
git status --short --branch
git ls-remote origin refs/heads/main
```

## 3. JWT signing key rotation

Recommended approach:

1. Set new `JWT_SIGNING_KEY`.
2. Force refresh token invalidation if compromise suspected.
3. Consider blacklisting outstanding refresh tokens.
4. Communicate re-login requirement.

## 4. Database password rotation

1. Create new DB credential.
2. Update secret manager/env.
3. Restart app/worker/beat.
4. Verify `/health/ready/`.
5. Revoke old credential.

## 5. S3 credential rotation

1. Create new access key.
2. Update env.
3. Restart app/worker.
4. Verify upload/download/signed URLs.
5. Disable old key.
