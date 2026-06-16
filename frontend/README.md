# بعثت مردم — Frontend (Next.js 15)

UI/UX رسمی پروژه **بعثت مردم** (ستاد جنگ). این پکیج، فرانت‌اند کاملاً جدا از بک‌اند Django/DRF است
و از طریق REST API به آن متصل می‌شود.

## استک

- **Next.js 15** (App Router, RSC, SSR/SSG)
- **TypeScript** strict
- **Tailwind CSS** + Design Tokens سفارشی (brand teal + accent amber)
- **Framer Motion** برای انیمیشن‌های روان (با احترام به `prefers-reduced-motion`)
- **lucide-react** برای آیکن‌ها
- **Vazirmatn** به‌عنوان فونت اصلی فارسی، RTL کامل
- **SEO پیشرفته**: metadata API، sitemap داینامیک، robots، manifest، JSON-LD (Organization, WebSite, FAQPage), OG/Twitter cards، canonical/alternate

## ساختار

```
frontend/
├── public/                   # favicon, logo, og images
├── src/
│   ├── app/                  # App Router pages
│   │   ├── layout.tsx        # Root layout + global SEO + Header/Footer
│   │   ├── page.tsx          # Home
│   │   ├── globals.css       # Tailwind + design system
│   │   ├── sitemap.ts        # Dynamic sitemap
│   │   ├── robots.ts
│   │   └── manifest.ts
│   ├── components/
│   │   ├── brand/Logo.tsx
│   │   ├── layout/Header.tsx
│   │   ├── layout/Footer.tsx
│   │   └── home/             # Home page sections (Hero, Pillars, ...)
│   └── lib/
│       ├── site.ts           # Single source of truth (branding/SEO)
│       ├── nav.ts            # Navigation config
│       ├── api.ts            # Typed DRF client + envelope unwrap
│       └── utils.ts          # cn(), Persian formatters
└── ...
```

## شروع توسعه

```bash
cd frontend
cp .env.example .env.local       # ست کردن NEXT_PUBLIC_API_URL
npm install
npm run dev                       # http://localhost:3000
```

> برای کانکت به بک‌اند، Django باید روی `NEXT_PUBLIC_API_URL` (پیش‌فرض: `http://localhost:8000`) در حال اجرا باشد.

## نقشه راه (همگام با اولویت پروژه)

- [x] **گام ۱ — پایه و Home**: design system، layout، Header/Footer، صفحه اصلی، SEO پایه (Sitemap، Robots، Manifest، JSON-LD، OG)
- [ ] **گام ۲ — Madadkar**: لیست کمپین‌ها، جزئیات، مشارکت، پرداخت، history (`/api/v1/madadkar/...`)
- [ ] **گام ۳ — Authentication**: signup OTP، login password/OTP، forgot/reset، profile (`/api/v1/auth/...`)
- [ ] **گام ۴ — Admin / Command Center**: command-center، admin daily ops
- [ ] **گام ۵ — LMS, Kindness Wall, R4J, Tabyin, Public Reports, Support Desk, Notifications**

## نکات SEO پیاده‌شده

- Metadata API کامل (title template, OG, Twitter, robots, canonical, alternate-language)
- Structured Data: `Organization`, `WebSite` (با SearchAction), `FAQPage`
- Sitemap داینامیک با changeFrequency/priority درست
- Robots با مسیرهای حساس مسدودشده (`/admin`, `/dashboard`, `/auth`, `/api/proxy`)
- Security headers (HSTS، XCO، Referrer, Permissions)
- Vazirmatn از CDN با `preconnect`
- a11y: skip-to-main، focus rings، prefers-reduced-motion

## ارتباط با بک‌اند

- پاسخ‌ها از Django طبق envelope زیر برمی‌گردد و توسط `apiFetch` به‌صورت typed unwrap می‌شود:
  ```json
  { "success": true, "status_code": 200, "message": "...", "data": {...} }
  ```
- در browser از مسیر same-origin `/api/proxy/...` (rewrite در `next.config.mjs`) استفاده می‌شود
  تا CORS و کوکی‌ها بدون درد سر مدیریت شوند.
