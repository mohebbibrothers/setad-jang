'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Menu, X, LogIn } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { TopBar } from './TopBar';
import { cn } from '@/lib/utils';

type NavItem = { label: string; href: string };

/**
 * Primary navigation — final spec from the client.
 *
 * RTL reading order (right → left visually): خانه · پشتیبانی مالی جنگ ·
 * جایزه‌ای برای عدالت · قرارگاه آموزشی · دیوار مهربانی · جهاد تبیین ·
 * ارتباط با ما.
 *
 * Hrefs are in-page anchors for the five domain sections (so the header
 * smooth-scrolls instead of jumping to a separate route) plus '/' for
 * 'خانه' and '/contact' for 'ارتباط با ما'. The delegated anchor handler
 * we already ship globally takes care of the smooth-scroll.
 */
const NAV: NavItem[] = [
  { label: 'خانه',                href: '/' },
  { label: 'پشتیبانی مالی جنگ',   href: '/#warfund' },
  { label: 'جایزه‌ای برای عدالت', href: '/#justice' },
  { label: 'قرارگاه آموزشی',      href: '/#education' },
  { label: 'دیوار مهربانی',       href: '/#kindness' },
  { label: 'جهاد تبیین',          href: '/#tabyin' },
  { label: 'ارتباط با ما',        href: '/contact' },
];

/** Smooth-scroll to the anchor when the user is already on '/'. Falls
 *  back to default <a> behaviour (cross-page nav) otherwise. */
function onNavClick(e: React.MouseEvent<HTMLAnchorElement>, href: string) {
  if (typeof window === 'undefined') return;
  if (!href.startsWith('/#')) return;
  if (window.location.pathname !== '/') return;
  const id = href.slice(2);
  const el = document.getElementById(id);
  if (!el) return;
  e.preventDefault();
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  window.history.replaceState(null, '', href);
}

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
              {NAV.map((item) => (
                <a
                  key={item.href + item.label}
                  href={item.href}
                  onClick={(e) => onNavClick(e, item.href)}
                  className="px-3.5 py-2 text-[14.5px] font-medium text-ink-700 rounded-lg
                             hover:text-brand-600 hover:bg-brand-50/60 transition-colors whitespace-nowrap"
                >
                  {item.label}
                </a>
              ))}
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
            {NAV.map((item) => (
              <a
                key={item.href + item.label}
                href={item.href}
                onClick={(e) => { onNavClick(e, item.href); setOpen(false); }}
                className="px-4 py-3 rounded-xl text-ink-800 hover:bg-brand-50 hover:text-brand-700
                           font-medium transition-colors"
              >
                {item.label}
              </a>
            ))}
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
