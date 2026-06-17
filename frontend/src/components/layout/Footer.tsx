import Image from 'next/image';
import Link from 'next/link';
import { Instagram, Twitter, Linkedin, Send } from 'lucide-react';

/**
 * Footer block that owns the newsletter pill.
 * Mirrors the designer's mockup exactly:
 *  - Independent white rounded card hosts the green newsletter pill
 *  - That white card sits centred above the bowed cutout of the ink-50 card
 *  - 4 link columns inside the ink-50 card
 *  - Bottom strip with logo + copyright + social — INSIDE the same card
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
    <footer className="relative bg-white pt-[4.5rem] md:pt-[5.5rem]">
      {/* Independent rounded pill wrapping the green newsletter.
          Lifted so the green pill sits HIGHER (white area + top of dip),
          which is more legible and matches the designer mockup proportions.
          Soft radial halo blends the white pill into ink-50 with no edge. */}
      <div
        className="absolute left-1/2 top-10 md:top-11 -translate-x-1/2 z-10
                   w-[min(620px,90vw)] md:w-[min(680px,80vw)]
                   rounded-full p-[10px] md:p-[12px] px-[14px] md:px-[16px]
                   before:content-[''] before:absolute before:inset-[-22px] before:-z-10
                   before:rounded-full before:pointer-events-none before:blur-[8px]
                   before:[background:radial-gradient(ellipse_70%_110%_at_center,rgba(255,255,255,0.70)_0%,rgba(255,255,255,0.35)_40%,rgba(255,255,255,0)_75%)]"
        style={{
          background:
            'radial-gradient(ellipse 75% 130% at center, #ffffff 50%, rgba(255,255,255,0.95) 68%, rgba(245,248,250,0.78) 84%, rgba(245,248,250,0) 100%)',
          boxShadow:
            '0 1px 3px -1px rgba(11,53,48,0.05), 0 12px 28px -14px rgba(11,53,48,0.12)',
        }}
      >
        <NewsletterPill />
      </div>

      {/* Light ink-50 card with the bowed top cutout from Asset 3 */}
      <div
        className="relative max-w-[1280px] mx-auto px-4 md:px-8 pt-24 md:pt-[6.5rem] pb-6 md:pb-8
                   bg-ink-50 rounded-t-[2rem] md:rounded-t-[2.5rem]"
        style={{
          backgroundImage: 'url(/brand/footer-newsletter-card.png)',
          backgroundSize: '100% 120px',
          backgroundRepeat: 'no-repeat',
          backgroundPosition: 'center top',
        }}
      >
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

/* Newsletter pill — green inner form. White card halo is provided
   by the parent <Footer/>. */
function NewsletterPill() {
  return (
    <form
      className="bg-brand-500 rounded-full flex items-center p-1.5 md:p-[7px] gap-2"
      aria-label="فرم خبرنامه"
    >
      <label htmlFor="footer-newsletter"
             className="px-4 md:px-6 text-white font-bold text-sm md:text-[15.5px] whitespace-nowrap">
        عضویت در خبرنامه
      </label>
      <div className="flex-1 bg-white rounded-full h-[40px] md:h-[42px] flex items-center px-4">
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
        className="inline-flex items-center gap-1.5 h-[40px] md:h-[42px] px-5 md:px-6 rounded-full
                   bg-gold-500 hover:bg-gold-600 text-ink-900 text-[13.5px] font-bold transition-colors shrink-0"
      >
        <Send className="w-4 h-4" strokeWidth={2.2} />
        ارسال
      </button>
    </form>
  );
}
