import Image from 'next/image';
import Link from 'next/link';
import { Instagram, Twitter, Linkedin, Send } from 'lucide-react';

/**
 * Footer block that owns the newsletter pill.
 * Mirrors the designer's mockup exactly:
 *  - Light grey rounded card with a small top cutout
 *  - Teal-coloured newsletter pill straddling the cutout
 *  - 4 link columns
 *  - Bottom strip with transparent logo + copyright + social
 */

const COLS = [
  {
    title: 'نحوه ثبت نام در پویش',
    links: [
      { label: 'پشتیبانی مالی جنگ', href: '/madadkar' },
      { label: 'دیوار مهربانی',     href: '/kindness-wall' },
      { label: 'قرارگاه آموزشی',    href: '/lms' },
    ],
  },
  {
    title: 'دسترسی سریع',
    links: [
      { label: 'جهاد تبیین',        href: '/tabyin' },
      { label: 'جایزه عدالت',       href: '/r4j' },
      { label: 'گزارش‌های مردمی',   href: '/public-reports' },
    ],
  },
  {
    title: 'درباره ما',
    links: [
      { label: 'معرفی بعثت مردم',   href: '/about' },
      { label: 'تماس با ما',        href: '/contact' },
      { label: 'سؤالات متداول',     href: '/faq' },
    ],
  },
  {
    title: 'قوانین و حمایت',
    links: [
      { label: 'حریم خصوصی',        href: '/privacy' },
      { label: 'قوانین و مقررات',   href: '/terms' },
      { label: 'پشتیبانی',          href: '/support' },
    ],
  },
];

export function Footer() {
  return (
    <footer className="bg-white pt-16 md:pt-20">
      {/* One unified ink-50 card. The cutout effect is rendered by the
          NewsletterPill below — a white rounded "halo" that floats above
          the card top edge and wraps the green pill (matches Asset 3). */}
      <div className="relative max-w-[1280px] mx-auto px-4 md:px-8 pt-16 md:pt-20 pb-6 md:pb-8
                      bg-ink-50 rounded-t-[2rem] md:rounded-t-[2.5rem]">
        {/* Newsletter pill — straddles the bowed cutout */}
        <NewsletterPill />

        {/* Footer columns */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-10 text-right">
          {COLS.map((c) => (
            <nav key={c.title} aria-label={c.title}>
              <h4 className="font-bold text-ink-900 mb-4 text-[14.5px]">{c.title}</h4>
              <ul className="space-y-2.5">
                {c.links.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} className="text-ink-500 hover:text-brand-600 text-[13.5px] transition-colors">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        {/* Bottom strip — INSIDE the same card, separated by a subtle hairline */}
        <div className="mt-10 md:mt-12 pt-6 md:pt-8 border-t border-black/[0.06]
                        flex flex-col md:flex-row items-center justify-between gap-5">
          <Link href="/" aria-label="بعثت مردم">
            <Image src="/brand/logo-mark.png" alt="بعثت مردم"
                   width={185} height={70}
                   className="h-10 w-auto" />
          </Link>
          <p className="text-[12.5px] text-ink-500 text-center">
            © ۱۴۰۵ بعثت مردم — تمامی حقوق محفوظ است. طراحی و توسعه با مهر برای مردم ایران.
          </p>
          <div className="flex items-center gap-2.5 text-ink-500">
            <Link href="#" aria-label="اینستاگرام" className="w-9 h-9 rounded-full bg-white border border-ink-200 hover:border-brand-300 hover:text-brand-600 flex items-center justify-center transition-colors">
              <Instagram className="w-4 h-4" />
            </Link>
            <Link href="#" aria-label="توییتر" className="w-9 h-9 rounded-full bg-white border border-ink-200 hover:border-brand-300 hover:text-brand-600 flex items-center justify-center transition-colors">
              <Twitter className="w-4 h-4" />
            </Link>
            <Link href="#" aria-label="لینکدین" className="w-9 h-9 rounded-full bg-white border border-ink-200 hover:border-brand-300 hover:text-brand-600 flex items-center justify-center transition-colors">
              <Linkedin className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

    </footer>
  );
}

/* Newsletter pill — sits inside a white rounded "halo" that nests
   into the top cutout of the footer card (matches designer Asset 3). */
function NewsletterPill() {
  return (
    <div
      className="relative z-[5] max-w-[720px] mx-auto -mt-[72px] md:-mt-[80px] mb-12 md:mb-16
                 bg-white rounded-[32px] md:rounded-[40px]
                 p-[14px] md:p-[16px] px-[18px] md:px-[22px]
                 shadow-[0_-2px_0_rgba(0,0,0,0.02)]"
    >
      <form
        className="bg-brand-500 rounded-full shadow-card flex items-center p-2 gap-2"
        aria-label="فرم خبرنامه"
      >
        <label htmlFor="footer-newsletter"
               className="px-4 md:px-6 text-white font-bold text-sm md:text-[15.5px] whitespace-nowrap">
          عضویت در خبرنامه
        </label>
        <div className="flex-1 bg-white rounded-full h-[42px] flex items-center px-4">
          <input
            id="footer-newsletter"
            type="email"
            required
            placeholder="آدرس ایمیل…"
            aria-label="آدرس ایمیل"
            dir="rtl"
            className="flex-1 h-full bg-transparent outline-none text-[13.5px]
                       text-ink-900 placeholder:text-ink-400 text-right"
          />
        </div>
        <button
          type="submit"
          className="inline-flex items-center gap-1.5 h-[42px] px-5 md:px-6 rounded-full
                     bg-gold-500 hover:bg-gold-600 text-ink-900 text-[13.5px] font-bold transition-colors shrink-0"
        >
          <Send className="w-4 h-4" strokeWidth={2.2} />
          ارسال
        </button>
      </form>
    </div>
  );
}
