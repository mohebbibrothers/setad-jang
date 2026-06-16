import Link from 'next/link';
import { Logo } from '@/components/brand/Logo';
import { Instagram, Twitter, Linkedin } from 'lucide-react';

const COLS = [
  {
    title: 'نحوه ثبت نام در پویش',
    links: [
      { label: 'پشتیبانی مالی جنگ', href: '/madadkar' },
      { label: 'دیوار مهربانی', href: '/kindness-wall' },
      { label: 'قرارگاه آموزشی', href: '/lms' },
    ],
  },
  {
    title: 'نحوه ثبت نام در پویش',
    links: [
      { label: 'جهاد تبیین', href: '/tabyin' },
      { label: 'جایزه عدالت', href: '/r4j' },
      { label: 'گزارش‌های مردمی', href: '/public-reports' },
    ],
  },
  {
    title: 'نحوه ثبت نام در پویش',
    links: [
      { label: 'درباره ما', href: '/about' },
      { label: 'تماس با ما', href: '/contact' },
      { label: 'سؤالات متداول', href: '/faq' },
    ],
  },
  {
    title: 'نحوه ثبت نام در پویش',
    links: [
      { label: 'حریم خصوصی', href: '/privacy' },
      { label: 'قوانین و مقررات', href: '/terms' },
      { label: 'پشتیبانی', href: '/support' },
    ],
  },
];

export function Footer() {
  return (
    <footer className="bg-ink-50 border-t border-ink-100">
      <div className="container-edge py-12 md:py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-10 mb-12">
          {COLS.map((c, i) => (
            <nav key={i} aria-label={c.title}>
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

        {/* Bottom bar */}
        <div className="pt-8 border-t border-ink-100 flex flex-col md:flex-row items-center justify-between gap-5">
          <Link href="/" aria-label="بعثت مردم">
            <Logo width={120} />
          </Link>

          <p className="text-[12.5px] text-ink-500 text-center">
            © ۱۴۰۵ بعثت مردم. تمامی حقوق محفوظ است. طراحی و توسعه با ❤️ برای مردم ایران.
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
    </footer>
  );
}
