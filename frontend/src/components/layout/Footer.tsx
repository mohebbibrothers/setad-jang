import Image from 'next/image';
import Link from 'next/link';
import { Instagram, Twitter, Linkedin } from 'lucide-react';

/**
 * Footer — clean two-block layout (newsletter pill removed).
 *
 * Layout:
 *   - Ink-50 card with rounded top corners hosts 4 link columns.
 *   - Bottom strip (inside the same card) holds the transparent
 *     logo-mark + copyright + social icons.
 *   - The bowed cutout image was tied to the newsletter pill above the
 *     card; without that pill the cutout is no longer needed, so the
 *     card simply rounds at the top — much cleaner silhouette.
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
    <footer className="relative bg-white pt-12 md:pt-16">
      <div
        className="relative max-w-[1280px] mx-auto px-5 md:px-8 pt-10 md:pt-14 pb-6 md:pb-8
                   bg-ink-50 rounded-t-[2rem] md:rounded-t-[2.5rem]"
      >
        {/* Footer columns */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-10 text-right">
          {COLS.map((c) => (
            <nav key={c.title} aria-label={c.title}>
              <h4 className="font-bold text-ink-900 mb-4 text-[14.5px]">{c.title}</h4>
              <ul className="space-y-2.5">
                {c.links.map((l) => (
                  <li key={l.href}>
                    <Link
                      href={l.href}
                      className="text-ink-500 hover:text-brand-600 text-[13.5px] transition-colors"
                    >
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
          <Link href="/" aria-label="بعثت مردم" className="shrink-0">
            <Image
              src="/brand/logo-mark.png"
              alt="بعثت مردم"
              width={185}
              height={70}
              className="h-12 w-auto"
            />
          </Link>
          <p className="text-[12.5px] text-ink-500 text-center">
            © ۱۴۰۵ بعثت مردم — تمامی حقوق محفوظ است. طراحی و توسعه با مهر برای مردم ایران.
          </p>
          <div className="flex items-center gap-2.5 text-ink-500">
            <Link
              href="#"
              aria-label="اینستاگرام"
              className="w-9 h-9 rounded-full bg-white border border-ink-200 hover:border-brand-300
                         hover:text-brand-600 flex items-center justify-center transition-colors"
            >
              <Instagram className="w-4 h-4" />
            </Link>
            <Link
              href="#"
              aria-label="توییتر"
              className="w-9 h-9 rounded-full bg-white border border-ink-200 hover:border-brand-300
                         hover:text-brand-600 flex items-center justify-center transition-colors"
            >
              <Twitter className="w-4 h-4" />
            </Link>
            <Link
              href="#"
              aria-label="لینکدین"
              className="w-9 h-9 rounded-full bg-white border border-ink-200 hover:border-brand-300
                         hover:text-brand-600 flex items-center justify-center transition-colors"
            >
              <Linkedin className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
