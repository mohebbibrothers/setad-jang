import Link from 'next/link';
import { Logo } from '@/components/brand/Logo';
import { Instagram, Twitter, Linkedin } from 'lucide-react';
import { NewsletterBar } from '@/components/home/NewsletterBar';

const COLS = [
  {
    title: 'فعالیت‌های کلیدی',
    links: [
      { label: 'پشتیبانی مالی جنگ', href: '/madadkar' },
      { label: 'دیوار مهربانی', href: '/kindness-wall' },
      { label: 'قرارگاه آموزشی', href: '/lms' },
    ],
  },
  {
    title: 'کاربست و رسانه',
    links: [
      { label: 'جهاد تبیین', href: '/tabyin' },
      { label: 'جایزه عدالت', href: '/r4j' },
      { label: 'گزارش‌های مردمی', href: '/public-reports' },
    ],
  },
  {
    title: 'درباره ما',
    links: [
      { label: 'معرفی بعثت مردم', href: '/about' },
      { label: 'تماس با ما', href: '/contact' },
      { label: 'سؤالات متداول', href: '/faq' },
    ],
  },
  {
    title: 'قوانین و حمایت',
    links: [
      { label: 'حریم خصوصی', href: '/privacy' },
      { label: 'قوانین و مقررات', href: '/terms' },
      { label: 'پشتیبانی', href: '/support' },
    ],
  },
];

/**
 * Newsletter+Footer composite — matches the designer mockup:
 *  - Outer light-grey container with a U-shaped notch carved out of the top
 *  - Newsletter pill sits inside the notch
 *  - Four link columns + bottom row (logo / copyright / social)
 */
export function Footer() {
  return (
    <section className="relative bg-white">
      <div className="relative bg-ink-50 rounded-t-[2rem] md:rounded-t-[2.5rem] pt-24 md:pt-28 pb-8 md:pb-12 overflow-hidden">
        {/* Notch carved out at top-center */}
        <div
          aria-hidden="true"
          className="absolute top-0 left-1/2 -translate-x-1/2 w-[340px] md:w-[520px] h-[42px] md:h-[52px]
                     bg-white rounded-b-full shadow-[inset_0_-1px_0_var(--ink-100,#EAEEF2)]"
        />

        {/* Newsletter — absolutely positioned to nest inside the notch */}
        <div className="absolute -top-3 md:-top-2 left-1/2 -translate-x-1/2 z-10
                        w-[calc(100%-2rem)] max-w-[600px] md:max-w-[680px]">
          <NewsletterBar />
        </div>

        <div className="container-edge">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-y-8 gap-x-6 lg:gap-x-12 mb-10">
            {COLS.map((c) => (
              <nav key={c.title} aria-label={c.title} className="text-right">
                <h4 className="font-extrabold text-ink-900 mb-4 text-[14.5px]">{c.title}</h4>
                <ul className="space-y-3">
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

          <div className="pt-8 border-t border-ink-200 flex flex-col md:flex-row items-center justify-between gap-5">
            <Link href="/" aria-label="بعثت مردم">
              <Logo width={130} transparent />
            </Link>

            <p className="text-[12.5px] text-ink-500 text-center">
              © ۱۴۰۵ بعثت مردم — تمامی حقوق محفوظ است. طراحی و توسعه با مهر برای مردم ایران.
            </p>

            <div className="flex items-center gap-3 text-ink-500">
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
      </div>
    </section>
  );
}
