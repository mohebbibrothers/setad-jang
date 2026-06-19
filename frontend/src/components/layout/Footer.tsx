import Image from 'next/image';
import Link from 'next/link';
import { Instagram, Twitter, Linkedin, Send } from 'lucide-react';

/**
 * Footer v3 — center-aligned, premium presentation.
 *
 * What changed vs v2:
 *   • Column content is fully CENTRED (was right-aligned). Titles get a
 *     short brand-tinted underline rule that doubles as a visual anchor.
 *   • The card sits on a soft brand-mint glow that fades in from the
 *     ink-50 base — adds depth without being noisy.
 *   • Bottom strip is restructured into three perfectly-balanced lanes
 *     (brand · copy · social) using a 1fr / auto / 1fr grid so the
 *     copyright always reads dead-centre regardless of column widths.
 *   • Social icons get an interactive disc treatment with a brand glow
 *     on hover — feels alive, not static.
 *   • A tiny "back to top" pill anchors the very bottom for ergonomics.
 */

const COLS = [
  {
    title: 'نحوه ثبت‌نام در پویش',
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

const SOCIALS = [
  { Icon: Instagram, label: 'اینستاگرام', href: '#' },
  { Icon: Twitter,   label: 'توییتر',     href: '#' },
  { Icon: Linkedin,  label: 'لینکدین',    href: '#' },
  { Icon: Send,      label: 'تلگرام',     href: '#' },
];

export function Footer() {
  return (
    <footer className="relative bg-white pt-12 md:pt-16">
      <div
        className="relative max-w-[1280px] mx-auto px-5 md:px-8 pt-12 md:pt-16 pb-7 md:pb-9
                   bg-ink-50 rounded-t-[2rem] md:rounded-t-[2.5rem] overflow-hidden"
      >
        {/* Soft brand glow — adds depth without distracting from the type */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 w-[80%] h-[260px]
                     rounded-full opacity-[0.16] blur-3xl"
          style={{
            background:
              'radial-gradient(ellipse at center, #25C5BA 0%, #0D8074 45%, transparent 70%)',
          }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, rgba(13,128,116,0.55) 1px, transparent 1px)',
            backgroundSize: '22px 22px',
          }}
        />

        {/* Footer columns — fully centred */}
        <div className="relative grid grid-cols-2 md:grid-cols-4 gap-10 md:gap-8 text-center">
          {COLS.map((c) => (
            <nav key={c.title} aria-label={c.title} className="flex flex-col items-center">
              <h4 className="font-extrabold text-ink-900 text-[14.5px] mb-1">{c.title}</h4>
              {/* Brand-tinted underline rule — short, decorative anchor */}
              <span
                aria-hidden="true"
                className="block h-[3px] w-9 rounded-full mb-5
                           bg-gradient-to-l from-brand-500 to-mint-500"
              />
              <ul className="space-y-3">
                {c.links.map((l) => (
                  <li key={l.href}>
                    <Link
                      href={l.href}
                      className="relative inline-block text-ink-500 hover:text-brand-700 text-[13.5px] font-medium
                                 transition-colors duration-200
                                 after:content-[''] after:absolute after:right-0 after:bottom-0 after:left-0
                                 after:h-px after:bg-brand-500 after:scale-x-0 hover:after:scale-x-100
                                 after:origin-center after:transition-transform after:duration-300"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        {/* Decorative divider — gradient hairline that fades at the edges */}
        <div
          aria-hidden="true"
          className="relative mt-12 md:mt-14 h-px"
          style={{
            background:
              'linear-gradient(to left, transparent, rgba(13,128,116,0.22), transparent)',
          }}
        />

        {/* Bottom strip — 3-lane perfectly balanced grid */}
        <div className="relative mt-7 md:mt-8 grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-6 items-center">
          {/* Lane 1 — brand mark, left-aligned in LTR / right-aligned in RTL */}
          <div className="flex justify-center md:justify-start">
            <Link href="/" aria-label="بعثت مردم" className="inline-flex">
              <Image
                src="/brand/logo-mark.png"
                alt="بعثت مردم"
                width={185}
                height={70}
                className="h-12 w-auto"
                priority={false}
              />
            </Link>
          </div>

          {/* Lane 2 — copyright, true centre */}
          <p className="text-[12.5px] text-ink-500 font-medium text-center leading-7">
            © ۱۴۰۵ بعثت مردم — تمامی حقوق محفوظ است.
            <span className="hidden md:inline"> · طراحی و توسعه با مهر برای مردم ایران.</span>
          </p>

          {/* Lane 3 — socials */}
          <div className="flex justify-center md:justify-end items-center gap-2.5">
            {SOCIALS.map(({ Icon, label, href }) => (
              <Link
                key={label}
                href={href}
                aria-label={label}
                className="group relative w-10 h-10 rounded-full bg-white text-ink-500
                           border border-ink-200
                           hover:text-white hover:border-transparent
                           flex items-center justify-center transition-all duration-300
                           shadow-[0_2px_8px_-3px_rgba(15,20,32,.08)]
                           hover:shadow-[0_10px_24px_-6px_rgba(13,128,116,.45)]
                           hover:-translate-y-0.5"
              >
                <span
                  aria-hidden="true"
                  className="absolute inset-0 rounded-full opacity-0 group-hover:opacity-100
                             transition-opacity duration-300
                             bg-gradient-to-br from-brand-500 to-brand-700"
                />
                <Icon className="relative w-[18px] h-[18px]" strokeWidth={2.1} />
              </Link>
            ))}
          </div>
        </div>

        {/* Back-to-top pill — tiny, polished ergonomics */}
        <div className="relative mt-7 flex justify-center">
          <a
            href="#main"
            className="inline-flex items-center gap-2 text-[12px] font-extrabold text-ink-500
                       hover:text-brand-700 transition-colors"
          >
            <span
              className="w-7 h-7 rounded-full bg-white border border-ink-200
                         flex items-center justify-center
                         shadow-[0_2px_6px_-3px_rgba(15,20,32,.10)]
                         transition-all duration-200
                         group-hover:border-brand-300"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="18 15 12 9 6 15" />
              </svg>
            </span>
            بازگشت به بالا
          </a>
        </div>
      </div>
    </footer>
  );
}
