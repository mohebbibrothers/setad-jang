// ============================================================================
// سناریوی بارِ ترکیبی — یافتۀ P3-23 فاز ۸ (بازنویسی F2 ممیزی ۲۰۲۶-۰۸-۳۰)
// ----------------------------------------------------------------------------
// نسخهٔ اولِ این فایل مسیر/فیلد را «حَدس» زده بود و checkها 404 را پاس
// می‌گرفتند — سبزِ بی‌معنا. حالا:
//   * مسیرها دقیقاً contractِ schema.yaml‌اند و یک گیتِ تستی
//     (tests/test_k6_loadtest_contract.py) همین را در CI میخکوب می‌کند؛
//   * checkها صراحتاً 404/405 را «شکست» می‌شمارند (route drift دیگر
//     پنهان نمی‌ماند).
//
// اجرا (staging فقط — روی production نه، چون throttle/سهم واقعی مصرف می‌شود):
//   docker run --rm -i \
//     -e BASE_URL=https://staging.besat.me \
//     -e LT_IDENTIFIER=09120000000 \
//     -e LT_OTP_CODE=123456 \
//     -e LT_ACCESS_TOKEN=<jwt-access> \
//     -e LT_CAMPAIGN_SLUG=<slug-kampan-e-azmouni> \
//     grafana/k6 run - < deploy/loadtest/k6_auth_participation.js
//
// LT_OTP_CODE فقط وقتی معنا دارد که سرویس OTP روی حالت test (کد ثابت از
// env/const) باشد؛ وگرنه verify عمداً 401 می‌گیرد که «نه ۵xx» = پاس است.
// ============================================================================
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://127.0.0.1:8000";
const IDENTIFIER = __ENV.LT_IDENTIFIER || "loadtest@besat.me";
const OTP_CODE = __ENV.LT_OTP_CODE || "";
const CAMPAIGN_SLUG = __ENV.LT_CAMPAIGN_SLUG || "loadtest-campaign";

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
    // آستانه‌ها با Performance Contractsِ خود پروژه هم‌راستا؛ تغییرِ یکی
    // بدونِ دیگری = شکستِ عمدیِ این اسکریپت (drift بار باید جیغ بکشد).
    otp_request_latency: ["p(95)<800"],
    participation_latency: ["p(95)<1200"],
    http_req_failed: ["rate<0.01"],
  },
};

// contract: 404/405 یعنی مسیر/رویه عوض شده — این «شکست» است، نه عبور.
function routeAlive(r) {
  return r.status !== 404 && r.status !== 405;
}

export function authFlow() {
  otpRequests.add(1);
  const t0 = Date.now();
  const req = http.post(
    `${BASE}/api/v1/auth/login/otp/request/`,
    JSON.stringify({ identifier: IDENTIFIER }),
    { headers: { "Content-Type": "application/json" }, tags: { flow: "otp_request" } },
  );
  // 429 زیر بارِ ۵۰× پاسِ معنادار است (throttle دارد کار می‌کند)؛ 5xx هرگز.
  check(req, {
    "otp request route alive": (r) => routeAlive(r),
    "otp request 2xx/429/400": (r) =>
      (r.status >= 200 && r.status < 300) || r.status === 429 || r.status === 400,
    "otp request no 5xx": (r) => r.status < 500,
  });
  otpLatency.add(Date.now() - t0);

  if (OTP_CODE && req.status === 200) {
    const ver = http.post(
      `${BASE}/api/v1/auth/login/otp/verify/`,
      JSON.stringify({ identifier: IDENTIFIER, code: OTP_CODE }),
      { headers: { "Content-Type": "application/json" }, tags: { flow: "otp_verify" } },
    );
    check(ver, {
      "verify route alive": (r) => routeAlive(r),
      "verify no 5xx": (r) => r.status < 500,
    });
  }
  sleep(Math.random() * 2);
}

export function participationFlow() {
  participationAttempts.add(1);
  const t0 = Date.now();
  const res = http.post(
    `${BASE}/api/v1/madadkar/campaigns/${encodeURIComponent(CAMPAIGN_SLUG)}/participate/`,
    JSON.stringify({ share_count: 1 }),
    {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${__ENV.LT_ACCESS_TOKEN || "loadtest-invalid-token"}`,
      },
      tags: { flow: "participate" },
    },
  );
  participationLatency.add(Date.now() - t0);
  // پاسخ‌های مجاز زیر بار: 2xx، 400 (اعتبارسنجی)، 401/403 (توکن ساختگی)،
  // 409 (سهم تمام/رقابت)، 429 (throttle). 404 = driftِ مسیر → شکستِ صریح.
  check(res, {
    "participate route alive": (r) => routeAlive(r),
    "participate no 5xx": (r) => r.status < 500,
  });
  sleep(Math.random());
}
