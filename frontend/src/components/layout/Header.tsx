'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Menu, X, ChevronDown, LogIn } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { TopBar } from './TopBar';
import { cn } from '@/lib/utils';

type NavItem = { label: string; href: string; children?: { label: string; href: string }[] };

/**
 * Primary navigation — labels and order follow the designer's mockup,
 * mapped to real backend apps under /api/v1/*.
 * "پروژه‌ها" has a dropdown that groups the multi-domain apps.
 */
const NAV: NavItem[] = [
  { label: 'خانه', href: '/' },
  { label: 'قرارگاه آموزشی', href: '/lms' },
  {
    label: 'پروژه‌ها',
    href: '#',
    children: [
      { label: 'مددکاری مالی', href: '/madadkar' },
      { label: 'دیوار مهربانی', href: '/kindness-wall' },
      { label: 'جهاد تبیین', href: '/tabyin' },
      { label: 'جایزه عدالت', href: '/r4j' },
      { label: 'گزارش‌های مردمی', href: '/public-reports' },
    ],
  },
  { label: 'دیوار مهربانی', href: '/kindness-wall' },
  { label: 'جهاد تبیین', href: '/tabyin' },
  { label: 'جایزه عدالت', href: '/r4j' },
];

export function Header() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  return (
    <>
      <div className={cn('sticky top-0 z-50', scrolled && 'shadow-sm')}>
        <TopBar />
        <header
          className={cn(
            'bg-white border-b border-ink-100 transition-shadow',
            scrolled ? 'shadow-soft' : '',
          )}
          role="banner"
        >
          <div className="container-edge h-16 lg:h-20 flex items-center gap-4">
            {/* Logo (RTL: visually right) */}
            <Link href="/" className="flex items-center shrink-0" aria-label="بعثت مردم — صفحه اصلی">
              <Logo width={120} priority />
            </Link>

            {/* Desktop nav (centered) */}
            <nav className="hidden lg:flex items-center gap-1 mx-auto" aria-label="ناوبری اصلی">
              {NAV.map((item) =>
                item.children ? (
                  <div key={item.label} className="relative group">
                    <button
                      className="inline-flex items-center gap-1 px-3.5 py-2 text-[15px] font-medium text-ink-700
                                 rounded-lg hover:text-brand-600 hover:bg-brand-50/60 transition-colors"
                    >
                      {item.label}
                      <ChevronDown className="w-4 h-4" />
                    </button>
                    <div className="absolute top-full right-0 mt-1 min-w-[200px] py-2 rounded-xl bg-white
                                    shadow-card border border-ink-100 opacity-0 invisible
                                    group-hover:opacity-100 group-hover:visible transition-all">
                      {item.children.map((c) => (
                        <Link
                          key={c.href}
                          href={c.href}
                          className="block px-4 py-2 text-[14px] text-ink-700 hover:bg-brand-50 hover:text-brand-700 transition-colors"
                        >
                          {c.label}
                        </Link>
                      ))}
                    </div>
                  </div>
                ) : (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="px-3.5 py-2 text-[15px] font-medium text-ink-700 rounded-lg
                               hover:text-brand-600 hover:bg-brand-50/60 transition-colors"
                  >
                    {item.label}
                  </Link>
                ),
              )}
            </nav>

            {/* Login CTA (left in RTL) */}
            <div className="mr-auto flex items-center gap-2">
              <Link
                href="/auth/login"
                className="hidden sm:inline-flex items-center gap-2 h-10 lg:h-11 px-5 lg:px-6
                           rounded-full bg-mint-500 hover:bg-mint-600 text-white font-semibold
                           shadow-soft transition-all"
              >
                <LogIn className="w-4 h-4" />
                ورود / ثبت‌نام
              </Link>

              <button
                type="button"
                className="lg:hidden w-11 h-11 inline-flex items-center justify-center rounded-xl
                           text-ink-800 hover:bg-ink-100 transition-colors"
                aria-label={open ? 'بستن منو' : 'باز کردن منو'}
                aria-expanded={open}
                onClick={() => setOpen((v) => !v)}
              >
                {open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
              </button>
            </div>
          </div>
        </header>
      </div>

      {/* Mobile sheet */}
      <div
        className={cn(
          'fixed inset-0 z-[60] lg:hidden transition-opacity duration-300',
          open ? 'opacity-100 visible' : 'opacity-0 invisible',
        )}
        aria-hidden={!open}
      >
        <button
          className="absolute inset-0 bg-ink-900/40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
          aria-label="بستن منو"
        />
        <aside
          className={cn(
            'absolute top-0 right-0 h-full w-[88%] max-w-sm bg-white shadow-float',
            'transition-transform duration-300 ease-out flex flex-col',
            open ? 'translate-x-0' : 'translate-x-full',
          )}
        >
          <div className="h-16 flex items-center justify-between px-4 border-b border-ink-100">
            <Logo width={100} />
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="w-10 h-10 inline-flex items-center justify-center rounded-lg hover:bg-ink-100"
              aria-label="بستن"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <nav className="flex-1 overflow-y-auto p-4 flex flex-col gap-1" aria-label="ناوبری موبایل">
            {NAV.flatMap((item) =>
              item.children
                ? [
                    { label: item.label, href: '#', heading: true as const },
                    ...item.children.map((c) => ({ ...c, heading: false as const, indent: true })),
                  ]
                : [{ ...item, heading: false as const }],
            ).map((item, i) =>
              'heading' in item && item.heading ? (
                <p key={`h-${i}`} className="px-4 mt-3 mb-1 text-xs font-bold text-ink-400 uppercase">
                  {item.label}
                </p>
              ) : (
                <Link
                  key={`l-${i}-${item.href}`}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className={cn(
                    'px-4 py-3 rounded-xl text-ink-800 hover:bg-brand-50 hover:text-brand-700 font-medium transition-colors',
                    'indent' in item && item.indent && 'pr-8 text-[14.5px]',
                  )}
                >
                  {item.label}
                </Link>
              ),
            )}
          </nav>
          <div className="p-4 border-t border-ink-100 flex flex-col gap-2">
            <Link href="/auth/login" className="inline-flex items-center justify-center gap-2 h-12
                                                rounded-full bg-mint-500 text-white font-semibold">
              <LogIn className="w-4 h-4" /> ورود / ثبت‌نام
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}
