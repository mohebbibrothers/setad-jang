# بعثت مردم — Frontend Release v1.0 (Homepage GA)

> **Tag**: `v1.0.0-homepage`
> **Target**: `https://setadjang.ir`
> **Backend**: `https://api.setadjang.ir`
> **Build**: Next.js 15.0.3 · React 19 RC · TypeScript strict · Tailwind 3.4

این release شامل **صفحه اصلی production-ready** است که تمام اپ‌های دامنه را با
backend واقعی sync می‌کند و در نبود داده، empty-state حرفه‌ای نمایش می‌دهد.

---

## 1. خلاصه‌ی اجرایی

| محور | وضعیت |
| ----- | ----- |
| Homepage UI/UX (همه‌ی سکشن‌ها) | ✅ آماده |
| Backend integration (real APIs) | ✅ Sync کامل |
| RTL / فارسی / Vazirmatn | ✅ |
| Empty states + dim pagers | ✅ |
| SEO (metadata, sitemap, robots, JSON-LD, OG) | ✅ |
| PWA manifest + favicons (192/512) | ✅ |
| Security headers (HSTS, X-Frame, CSP-friendly) | ✅ |
| ISR revalidation (180–600s) | ✅ |
| Production build (`npm run build` green) | ✅ بدون خطا |
| صفحات داخلی (auth/madadkar/r4j/...) | ⏳ Phase 2 |

---

## 2. قابلیت‌های sync‌شده با Backend (✅ کامل)

### 2.1 پشتیبانی مالی جنگ (`apps/madadkar`)
- ✅ `GET /madadkar/campaigns/` → کارت‌های کمپین (cover, sponsor logo, progress, participantCount, deadline, statusDisplay)
- ✅ `GET /madadkar/campaigns/<slug>/` → آلبوم ۳D Coverflow (gallery_images)
- ✅ `POST /madadkar/campaigns/<slug>/participate/` → فرم «خرید سهم» با همه‌ی validatorها
  - Slider/Stepper/Quick chips برای انتخاب share_count
  - Live bill: تومان + ریال (×۱۰) + درصد از کل
  - Mobile + email optional با validate سمت کلاینت
  - Handle errors: `InvalidShareCountError`, `CampaignNotAcceptingSharesError`, `InsufficientSharesError`, `PaymentGatewayError`
  - Redirect خودکار به `gateway_url`
  - Security strip: «۱۵ دقیقه رزرو سهم»
- ✅ Empty state اختصاصی: «هنوز حرکتی منتشر نشده»

### 2.2 جایزه‌ای برای عدالت (`apps/r4j`)
- ✅ `GET /r4j/criminals/` → کارت مجرم (slug, primary_photo, total_bounty_toman, bounties_count)
- ✅ `GET /r4j/criminals/<slug>/` (در آلبوم استفاده می‌شود)
- ✅ split-action popover «مشارکت در مجازات»
- ✅ Filter surface ready: `country`, `province`, `city`, `gender`, `search`
- ✅ Empty state: «هنوز پرونده‌ای منتشر نشده»

### 2.3 قرارگاه آموزشی (`apps/lms`)
- ✅ `GET /lms/categories/` → tabs (شمارنده‌ی **همیشه نمایان** حتی صفر)
- ✅ `GET /lms/courses/` → کارت‌های دوره (cover, instructor, level, lessons, duration, enrollments)
- ✅ Auto-derived `isNew` (publish < 30 روز) و `isFeatured` (enrollments > میانگین)
- ✅ Horizontal-only tab strip با scroll arrows
- ✅ Empty state: «هنوز دوره‌ای منتشر نشده»

### 2.4 دیوار مهربانی (`apps/kindness_wall`)
- ✅ `GET /kindness-wall/listings/` → ۳-grid با split-action «ثبت آگهی جدید»
- ✅ Normalize `listing_type` (`need_help` → `need`, `offer_help` → `offer`)
- ✅ Segmented switcher موبایل با counter chip
- ✅ Empty state: «هنوز آگهی منتشر نشده»

### 2.5 جهاد تبیین (`apps/tabyin`)
- ✅ `GET /tabyin/contents/` → masonry با 10 tile per page (2 tall + 8 short)
- ✅ Filter strip: همه / تصویر / ویدئو / صوت → `media_type` query param
- ✅ Sparse-mode auto-centering وقتی items < cols
- ✅ Surface: `external_id`, `primary_media_type`, `attachments`, `source_url`, `author_username`, `origin`
- ✅ Empty state **حالا dead-center** (grid-column: 1/-1 + grid-row: 1/span 3)

### 2.6 گزارش مردمی (`apps/public_reports`)
- ✅ `GET /public-reports/subjects/` → custom dropdown listbox
- ✅ `POST /public-reports/reports/` (multipart با FormData)
- ✅ Validators سمت کلاینت: `jpg/jpeg/png/webp`, max 5MB, max 5 attachments
- ✅ Required: `full_name (≤150)`, `subject_id`, `description`
- ✅ Optional: `phone_number (≤14)`, `attachments[]`
- ✅ Slide-to-verify با ResizeObserver
- ✅ Subject dropdown empty: «دسته‌بندی‌ای یافت نشد»

### 2.7 Layout & Branding
- ✅ Header: 7 nav item + mobile sheet + لوگو لینک به `/`
- ✅ TopBar: 4 partner strip (رسانه‌ی رهبر انقلاب / رسانه‌ی رهبر شهید / جانفدا / جهادآرا)
- ✅ Footer v3: مرکز‌چین، 4 ستون، BackToTop client island
- ✅ Hero: defenders image + animation با احترام به `prefers-reduced-motion`
- ✅ ActivitiesPanel: 5 آیکن (تبیین/مهربانی/lms/r4j/warfund) با anchor scroll
- ✅ Brand palette کامل: brand-500 `#0D8074`, mint-500 `#25C5BA`, accent-500 `#FF6B1A`, gold-500 `#FFB033`
- ✅ Vazirmatn FD v33.003

### 2.8 SEO + PWA
- ✅ `metadata` API (title, description, OG, Twitter)
- ✅ `sitemap.xml` داینامیک
- ✅ `robots.txt`
- ✅ `manifest.webmanifest` با icons (any + maskable, جدا شده — purpose: 'any maskable' دیگر نیست)
- ✅ `favicon.svg` + `favicon-192.png` + `favicon-512.png` + `favicon.ico`
- ✅ `/og/cover.png` (1200×630) ساخته شد
- ✅ `theme-color: #1F8A7A`

### 2.9 Security + Performance
- ✅ Headers (next.config.mjs): HSTS, X-Frame, X-Content-Type, Referrer-Policy, Permissions-Policy
- ✅ `images.formats: avif + webp`
- ✅ `optimizePackageImports: lucide-react + framer-motion`
- ✅ API proxy rewrite: `/api/proxy/*` → backend
- ✅ ISR revalidate per loader (180–600s)
- ✅ Production build: **75.4 kB صفحه + 100 kB shared = 197 kB First Load JS** ⚡

---

## 3. قابلیت‌های آماده‌ولی-منتظر-بک‌اند (🟡)

این بخش‌ها کاملاً client-ready هستند ولی هنوز endpoint بک‌اندی هم‌سویی ندارند یا
آماده‌سازی نهایی روی بک‌اند نشده:

| قابلیت | وضعیت | اقدام لازم |
| ------ | ----- | ---------- |
| Auth flow (signup/login/OTP) | endpointها روی بک‌اند هست، صفحه فرانت نه | Phase 2 — `/auth/*` pages |
| Kindness Wall `me/listings` (CRUD آگهی) | endpoint ✅، UI فرانت ❌ | Phase 2 — `/kindness-wall/me/*` |
| LMS enrollment + progress + certificate | endpoint ✅، UI فرانت ❌ | Phase 2 — `/lms/me/*` |
| Tabyin user submissions | endpoint ✅، UI فرانت ❌ | Phase 2 — `/tabyin/new` |
| Support desk (tickets + knowledge) | endpoint ✅، UI فرانت ❌ | Phase 2 — `/support/*` |
| Notifications inbox | endpoint ✅، UI فرانت ❌ | Phase 2 — `/notifications` |
| Command center summary | endpoint ✅، UI فرانت ❌ | Phase 3 — `/admin/*` |
| Activity timelines (me/admin) | endpoint ✅، UI فرانت ❌ | Phase 2 — `/dashboard` |
| R4J detail page | endpoint ✅، UI فرانت ❌ | Phase 2 — `/r4j/[slug]` |
| Madadkar detail page | endpoint ✅، UI فرانت partial (modal only) | Phase 2 — `/madadkar/[slug]` |

---

## 4. قابلیت‌هایی که در v1.0 **شامل نمی‌شود** (Phase 2/3)

### Phase 2 — صفحات داخلی (after homepage ships)
1. **Auth pages** — `/auth/signup`, `/auth/login`, `/auth/otp`, `/auth/forgot-password`
   - Multi-identifier (email + phone E.164)
   - OTP 5-digit با countdown ۶۰s
   - JWT refresh flow
   - sessions list `/auth/sessions/`
2. **User dashboard** — `/dashboard`
   - Activity timeline (`/activity/me/`)
   - Notification inbox (`/notifications/me/`)
   - Quick links به enrollments / bookmarks / matches / tickets
3. **Domain index pages** — `/madadkar`, `/r4j`, `/lms`, `/kindness-wall`, `/tabyin`
   - List + advanced filters
   - Pagination + sorting
4. **Detail pages** — `/madadkar/[slug]`, `/r4j/[slug]`, `/lms/courses/[slug]`, `/lms/courses/[slug]/lessons/[lessonSlug]`, `/kindness-wall/[slug]`, `/tabyin/[externalId]`
   - Full gallery
   - Comments / questions
   - Contextual CTAs
5. **Submission flows** — `/tabyin/new`, `/kindness-wall/new`
   - Multi-step wizard
   - Live validation با اعتبار سرور
6. **Support desk** — `/support`, `/support/tickets/[number]`
7. **Static pages** — `/about`, `/contact`, `/privacy`, `/terms`, `/faq`
   - Markdown-driven content
   - JSON-LD `FAQPage`, `ContactPage`

### Phase 3 — Power features
1. **Admin/Command-center UI** — `/admin/*`
2. **Search** — `/search` با FTS + filters
3. **R4J detail map** — Leaflet map با مختصات
4. **LMS quiz player** — interactive quiz + certificate
5. **Madadkar gateway return handler** — `/madadkar/return/*`
6. **i18n** — اگر بخواهید نسخه انگلیسی (در حال حاضر فقط فارسی)

---

## 5. چک‌لیست Deploy

### قبل از deploy (یک‌بار)
- [x] `frontend/.env.production` ساخته شود از روی `.env.production.example`
- [x] `NEXT_PUBLIC_SITE_URL=https://setadjang.ir`
- [x] `NEXT_PUBLIC_API_URL=https://api.setadjang.ir`
- [x] DNS A/AAAA رکورد `setadjang.ir` → سرور frontend
- [x] DNS A/AAAA رکورد `api.setadjang.ir` → سرور backend
- [x] گواهی SSL Let's Encrypt (یا Cloudflare) برای هر دو دامنه
- [x] CORS بک‌اند پذیرای `https://setadjang.ir` باشد

### Build + Run
```bash
cd frontend
npm ci --legacy-peer-deps     # peer دو پکیج روی React 18/19 conflict دارند
npm run build                  # → .next/  (197 kB First Load JS)
npm run start                  # → :3000
```

### پشت Nginx (recommended)
```nginx
server {
  listen 443 ssl http2;
  server_name setadjang.ir www.setadjang.ir;

  ssl_certificate     /etc/letsencrypt/live/setadjang.ir/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/setadjang.ir/privkey.pem;

  # gzip / brotli
  gzip on;
  gzip_types text/plain application/javascript application/json text/css image/svg+xml;

  location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  # Static assets از Next.js (با cache طولانی)
  location /_next/static/ {
    proxy_pass http://127.0.0.1:3000;
    proxy_cache_valid 200 1y;
    add_header Cache-Control "public, max-age=31536000, immutable";
  }
}
```

### Docker (alternative)
از Dockerfile نمونه در `DEPLOY.md` استفاده شود.

### Post-deploy smoke tests
```bash
curl -I https://setadjang.ir/                        # 200
curl -I https://setadjang.ir/sitemap.xml             # 200
curl -I https://setadjang.ir/robots.txt              # 200
curl -I https://setadjang.ir/manifest.webmanifest    # 200
curl -I https://setadjang.ir/favicon.svg             # 200
curl -I https://setadjang.ir/og/cover.png            # 200
curl  https://setadjang.ir/api/proxy/madadkar/campaigns/  # JSON envelope
```

---

## 6. Known Issues / Notes

1. **Next.js 15.0.3 CVE-2025-66478** — هشدار upgrade منتشر شده. در نسخه‌ی بعدی
   مهاجرت به `15.5.x` پیشنهاد می‌شود (نیاز به یک سری minor تغییر در fetch types).
2. **lucide-react peer-dep** — به‌خاطر React 19 RC نیاز به `--legacy-peer-deps` در `npm ci` هست.
   در Phase 2 با اصلاح به `react@19 stable` این مشکل برطرف می‌شود.
3. **Domain index pages** — لینک‌های `/madadkar`, `/r4j`, `/lms`, `/kindness-wall`, `/tabyin`,
   `/contact`, `/auth/login`, `/search` در v1.0 صفحه‌ی not-found می‌دهند (با طراحی زیبا).
   این کاملاً عمدی است — تمرکز v1.0 روی صفحه اصلی است.
4. **OG image** — یک نسخه‌ی SVG → PNG ۱۲۰۰×۶۳۰ ساخته شد. اگر تیم برند نسخه‌ی
   حرفه‌ای‌تری ارسال کرد، فقط جایگزین `/public/og/cover.png` کنید.

---

## 7. تأیید پایانی

**نقاط افتخار v1.0:**
- 🎯 صفر داده‌ی mock در production — هر سکشن یا داده‌ی واقعی نشان می‌دهد یا empty state حرفه‌ای
- 🎨 طراحی pixel-perfect designer-faithful برای هر ۵ سکشن دامنه
- 🚀 First Load JS فقط 197 kB (زیر آستانه‌ی Lighthouse "good")
- ♿ a11y: `aria-label`، `prefers-reduced-motion`، keyboard navigation در همه modals
- 🌐 SEO کامل: sitemap, robots, manifest, JSON-LD, OG, Twitter, canonical
- 🔒 Security headers default-on
- 📱 Full responsive: mobile (2-col) → tablet (3-col) → desktop (4-col)
- 🎬 Framer Motion animations روان همراه با reduced-motion fallback
- 🧪 Empty-state polish: dead-center icon + متن + dim pagers + dropdown empty

**ready to ship 🚀**
