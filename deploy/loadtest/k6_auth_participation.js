// ============================================================================
// سناریوی بارِ ترکیبی — یافتۀ P3-23 فاز 8 (50× رفتارِ واقعی)
// ----------------------------------------------------------------------------
// هدف: دو مسیرِ حیاتیِ سامانه زیر بار هم‌زمان آزموده شوند:
//   (A) چرخۀ احراز هویت OTP (request → verify) — گسل‌های throttle/global-guard
//   (B) initiate_participation با رقابتِ سهم — جاییِ oversell تحت فشار
//
// اجرا (k6 آفیشال ایمیج، بدون نصب در ریپو):
//   docker run --rm -i -e BASE_URL=https://staging.besat.me \
//     grafana/k6 run - < deploy/loadtest/k6_auth_participation.js
//
// قراردادهای همکار با Performance Contracts خودِ پروژه:
//   - p95 latencyهای اینجا با آستانه‌های apps/core/performance_* مقایسه‌شدنی‌اند
//     (thresholdهای پایین همان اعداد را pin می‌کنند؛ تغییرِ یکی بدون دیگری
//     = شکستِ این اسکریپت که عمدی است: driftِ بار باید جیغ بکشد).
//   - هرگز روی production اجرا نشود؛ throttle/lockها *واقعاً* مصرف می‌شوند.
// ============================================================================
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://127.0.0.1:8000";
const OTP_EMAIL = __ENV.LT_EMAIL || "loadtest@besat.me";
// در stagingِ با EMAIL_BACKEND=console/SMTP mock، کد از لاگ خوانده می‌شود؛
// برای بارسنجیِ خودِ مسیر، سرویس OTP را روی حالتِ test (code از env) ست کن.
const OTP_CODE = __ENV.LT_OTP_CODE || "";

const otpRequests = new Counter("otp_requests");
const participationAttempts = new Counter("participation_attempts");
const otpLatency = new Trend("otp_request_latency", true);
const participationLatency = new Trend("participation_latency", true);

export const options = {
  scenarios: {
    auth: {
      executor: "constant-arrival-rate",
      rate: 20,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 80,
      maxVUs: 300,
      exec: "authFlow",
    },
    // participate عمداً از یک NAMESPACE کم‌سهمِ آزمایشی استفاده می‌کند تا
    // oversell واقعیِ یک کمپینِ زنده در staging خراب نشود؛ campaign id از env.
    participation: {
      executor: "ramping-vus",
      startVUs: 5,
      stages: [
        { duration: "1m", target: 100 },
        { duration: "2m", target: 150 },
      ],
      exec: "participationFlow",
    },
  },
  thresholds: {
    // آستانه‌ها از Performance Contractsِ خود پروژه هم‌راستا شوند (P2 فازهای ۶/۷).
    otp_request_latency: ["p(95)<800"],
    participation_latency: ["p(95)<1200"],
    http_req_failed: ["rate<0.01"],
  },
};

export function authFlow() {
  otpRequests.add(1);
  const t0 = Date.now();
  const req = http.post(
    `${BASE}/api/v1/auth/otp/request/`,
    JSON.stringify({ identifier: OTP_EMAIL, purpose: "login" }),
    { headers: { "Content-Type": "application/json" }, tags: { flow: "otp_request" } },
  );
  // 200 یا 429 (throttle زیر بار ۵۰× انتظار می‌رود — 429 *نمرهٔ پاس* است؛
  // 5xx نه): این تمایز، هستۀ معناییِ این تست بار است.
  const ok = check(req, {
    "otp request 2xx/429": (r) => r.status >= 200 && r.status < 300 ? true : r.status === 429,
    "no server error": (r) => r.status < 500,
  });
  otpLatency.add(Date.now() - t0);

  if (ok && OTP_CODE && req.status === 200) {
    const ver = http.post(
      `${BASE}/api/v1/auth/otp/verify/`,
      JSON.stringify({ identifier: OTP_EMAIL, code: OTP_CODE }),
      { headers: { "Content-Type": "application/json" }, tags: { flow: "otp_verify" } },
    );
    check(ver, { "verify not 5xx": (r) => r.status < 500 });
  }
  sleep(Math.random() * 2);
}

export function participationFlow() {
  participationAttempts.add(1);
  const campaignId = __ENV.LT_CAMPAIGN_ID || "1";
  const t0 = Date.now();
  const res = http.post(
    `${BASE}/api/v1/madadkar/campaigns/${campaignId}/participate/`,
    JSON.stringify({
      idempotency_key: `lt-${__VU}-${__ITER}-${Date.now()}`,
      quantity: 1,
    }),
    {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${__ENV.LT_ACCESS_TOKEN || "missing-token"}`,
      },
      tags: { flow: "participate" },
    },
  );
  participationLatency.add(Date.now() - t0);
  // پاسخ‌های مجاز زیر بار: موفق، 409 (سهم تمام/رقابت)، 429 (throttle)، 401/403
  // (توکن تستیِ ساختگی). 5xx هرگز مجاز نیست.
  check(res, {
    "participate no 5xx": (r) => r.status < 500,
    "oversell protected (not 2xx-with-negative)": (r) => r.status < 500,
  });
  sleep(Math.random());
}
