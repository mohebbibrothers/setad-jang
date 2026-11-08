<?php
/**
 * index.php - thin proxy from Apache/PHP to the Django WSGI app.
 *
 * WHY THIS EXISTS
 * ---------------
 * The new cPanel host has no Passenger, so Django cannot be served by Apache
 * directly. `scripts/serve_gunicorn.sh` runs the WSGI app on 127.0.0.1:8765, and
 * this file forwards every request to it. It is deliberately small and boring:
 *
 *   - streams the body through (no size limit, no memory blowup)
 *   - preserves method, query string, headers and cookies
 *   - replaces Host/X-Forwarded-* so Django sees the real public host and scheme
 *   - forwards status code, content-type and a small allowlist of headers back
 *   - never leaks the internal port or a PHP stack trace to the client
 *
 * /media/* and /static/* never reach here - Apache serves them from disk
 * (see .htaccess) which is both faster and safer.
 */

declare(strict_types=1);

// ---------------------------------------------------------------- configuration
const UPSTREAM_HOST = '127.0.0.1';
const UPSTREAM_PORT = 8765;
const CONNECT_TIMEOUT_MS = 5000;
const TOTAL_TIMEOUT_SEC = 120;

/** Headers we forward to Django. Everything else (hop-by-hop) is dropped. */
const FORWARD_REQUEST_HEADERS = [
    'accept',
    'accept-encoding',
    'accept-language',
    'authorization',
    // NOTE: `content-type` is deliberately NOT here. It is handled by its own
    // block below, because a header that is emitted twice makes LiteSpeed
    // answer the whole request with
    //     400 Bad Request — Invalid HTTP Header: 'CONTENT-TYPE'
    // and that is exactly what broke every POST (login, listing upload) once
    // getallheaders() was added as a header source.
    'cookie',
    'if-none-match',
    'if-modified-since',
    'range',
    'user-agent',
    'x-requested-with',
    'x-viewer-id',
    'x-csrftoken',
    // ─── CSRF (the "403 CSRF verification failed" on the admin login) ───
    // Django validates unsafe requests against Origin, and falls back to
    // Referer when Origin is absent. An allowlist that dropped both made every
    // POST look like a cross-site forgery: the admin login form returned 403
    // while every GET worked. These four are not optional.
    'origin',
    'referer',
    'x-request-id',
    'x-forwarded-proto',
];

/** Headers we forward back to the client. */
const FORWARD_RESPONSE_HEADERS = [
    'content-type',
    'content-disposition',
    'cache-control',
    'etag',
    'last-modified',
    'vary',
    'location',
    'retry-after',
    'content-language',
    'x-frame-options',
    'x-content-type-options',
    'referrer-policy',
    'permissions-policy',
    'strict-transport-security',
    'set-cookie',
    'www-authenticate',
];

// ---------------------------------------------------------------- helpers

/** Emit a minimal JSON error so clients (and Vercel) never see a PHP trace. */
function proxy_fail(int $status, string $code): void
{
    if (!headers_sent()) {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
    }
    echo json_encode(
        [
            'success' => false,
            'status_code' => $status,
            'message' => $code === 'upstream_unreachable'
                ? 'سرویس بک‌اند در دسترس نیست.'
                : 'خطای درگاه بک‌اند.',
            'errors' => ['detail' => $code],
            'data' => null,
        ],
        JSON_UNESCAPED_UNICODE
    );
    exit;
}

/** Read the request body exactly once (works for chunked and Content-Length). */
function read_body(): string
{
    $body = file_get_contents('php://input');
    return $body === false ? '' : $body;
}

// ---------------------------------------------------------------- request

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$uri = $_SERVER['REQUEST_URI'] ?? '/';

// Rebuild the public URL for Django (it validates Host against ALLOWED_HOSTS).
$publicHost = $_SERVER['HTTP_HOST'] ?? 'localhost';
$isHttps = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
    || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https')
    || (($_SERVER['SERVER_PORT'] ?? '') === '443');
$scheme = $isHttps ? 'https' : 'http';

/**
 * Read an incoming request header from EVERY place PHP may have put it.
 *
 * THE BUG THIS FIXES (it cost us a whole "the user is logged out instantly"
 * incident): behind Apache/LiteSpeed with PHP as CGI/FastCGI, the
 * `Authorization` header is NOT exposed as `$_SERVER['HTTP_AUTHORIZATION']` -
 * Apache strips it unless the vhost explicitly passes it through. The proxy
 * therefore forwarded every request WITHOUT credentials:
 *
 *      GET /api/v1/auth/me  (Bearer <valid token>)
 *        -> Django: 401 "no authentication credentials were provided"
 *        -> the SPA treats 401 as "session dead" -> clears the tokens
 *        -> the user sees «خوش آمدید» and is signed out in the same breath.
 *
 * It also explains the 403 on every write (the admin form upload): a request
 * with no identity cannot pass an authenticated permission class.
 *
 * Sources tried, in order: HTTP_*, REDIRECT_HTTP_* (after an internal
 * rewrite), getallheaders() (LiteSpeed/apache2handler), the mod_rewrite
 * environment variable trick (see .htaccess), and finally PHP_AUTH_*.
 */
function incoming_header(string $name): ?string
{
    $key = 'HTTP_' . strtoupper(str_replace('-', '_', $name));
    foreach ([$key, 'REDIRECT_' . $key] as $candidate) {
        if (!empty($_SERVER[$candidate])) {
            return (string) $_SERVER[$candidate];
        }
    }
    if (function_exists('getallheaders')) {
        $all = getallheaders();
        if (is_array($all)) {
            foreach ($all as $rawName => $value) {
                if (strcasecmp((string) $rawName, $name) === 0 && $value !== '') {
                    return (string) $value;
                }
            }
        }
    }
    if ($name === 'authorization' && !empty($_SERVER['PHP_AUTH_USER'])) {
        return 'Basic ' . base64_encode(
            $_SERVER['PHP_AUTH_USER'] . ':' . ($_SERVER['PHP_AUTH_PW'] ?? '')
        );
    }
    return null;
}

/**
 * Build the upstream headers through a MAP keyed by the lower-cased name.
 *
 * A plain list let the same header be appended twice (e.g. getallheaders()
 * and the CONTENT_TYPE fallback both supplying content-type). Apache/LiteSpeed
 * reject a duplicated Content-Type with
 *     `400 Bad Request — Invalid HTTP Header: 'CONTENT-TYPE'`
 * before PHP ever sees the body, so the fix is structural: one key, one value.
 */
$forward = [];
foreach (FORWARD_REQUEST_HEADERS as $name) {
    $value = incoming_header($name);
    if ($value !== null) {
        $forward[strtolower($name)] = $value;
    }
}
$contentType = incoming_header('content-type');
if ($contentType === null && isset($_SERVER['CONTENT_TYPE'])) {
    $contentType = (string) $_SERVER['CONTENT_TYPE'];
}
if ($contentType !== null && $contentType !== '') {
    $forward['content-type'] = $contentType;
}
// Never let cURL send `Expect: 100-continue` for big uploads: some CGI stacks
// answer it with a 417 and the body is lost (a very confusing CSRF failure).
$headers = [];
foreach ($forward as $name => $value) {
    $headers[] = $name . ': ' . $value;
}
$headers[] = 'Expect:';

$clientIp = $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '';
$headers[] = 'Host: ' . $publicHost;
if (!isset($_SERVER['HTTP_X_FORWARDED_PROTO'])) {
    $headers[] = 'X-Forwarded-Proto: ' . $scheme;
}
$headers[] = 'X-Forwarded-Host: ' . $publicHost;
$headers[] = 'X-Forwarded-For: ' . $clientIp;
$headers[] = 'X-Real-IP: ' . ($_SERVER['REMOTE_ADDR'] ?? '');
$headers[] = 'Connection: close';

$body = read_body();
if ($body !== '') {
    $headers[] = 'Content-Length: ' . strlen($body);
}

// ---------------------------------------------------------------- upstream call

$upstreamStatus = 0;   // filled by the header callback (see below)
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => 'http://' . UPSTREAM_HOST . ':' . UPSTREAM_PORT . $uri,
    CURLOPT_CUSTOMREQUEST => $method,
    CURLOPT_HTTPHEADER => $headers,
    CURLOPT_CONNECTTIMEOUT_MS => CONNECT_TIMEOUT_MS,
    CURLOPT_TIMEOUT => TOTAL_TIMEOUT_SEC,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_HEADER => false,
    CURLOPT_RETURNTRANSFER => false,
    CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
    // stream the upstream body straight to the client
    CURLOPT_WRITEFUNCTION => static function ($handle, string $chunk): int {
        echo $chunk;
        flush();
        return strlen($chunk);
    },
    CURLOPT_HEADERFUNCTION => static function ($handle, string $line) use (&$upstreamStatus): int {
        $trimmed = trim($line);
        if ($trimmed === '') {
            return strlen($line);
        }
        if (str_starts_with($trimmed, 'HTTP/')) {
            // The status line arrives BEFORE any body byte. This is the only
            // moment the status can still be set: once the streaming write
            // callback has echoed data, PHP has already sent the headers and
            // http_response_code() silently does nothing.
            $parts = explode(' ', $trimmed);
            $upstreamStatus = (int) ($parts[1] ?? 0);
            if ($upstreamStatus > 0) {
                http_response_code($upstreamStatus);
            }
            return strlen($line);
        }
        [$name] = explode(':', $trimmed, 2);
        $lower = strtolower(trim($name));
        // Hop-by-hop and rewrite-sensitive headers are managed by us / Apache.
        if (in_array($lower, ['transfer-encoding', 'connection', 'content-length', 'date', 'server'], true)) {
            return strlen($line);
        }
        if (in_array($lower, FORWARD_RESPONSE_HEADERS, true)) {
            header($trimmed, false);
        }
        return strlen($line);
    },
]);

if ($body !== '') {
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
}

$started = curl_exec($ch);
$status = $upstreamStatus > 0 ? $upstreamStatus : (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);

if ($started === false) {
    $errno = curl_errno($ch);
    curl_close($ch);
    proxy_fail($errno === CURLE_OPERATION_TIMEDOUT ? 504 : 502, 'upstream_unreachable');
}

curl_close($ch);

if ($status === 0) {
    proxy_fail(502, 'upstream_unreachable');
}

// Kept as a safeguard for responses with an empty body (headers not sent yet).
if (!headers_sent()) {
    http_response_code($status);
}
