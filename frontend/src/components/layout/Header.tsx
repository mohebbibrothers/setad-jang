'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Menu, Search, X, LogIn, Bell } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { primaryNav } from '@/lib/nav';
import { cn } from '@/lib/utils';

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
      <header
        className={cn(
          'fixed top-0 inset-x-0 z-50 transition-all duration-300',
          scrolled
            ? 'bg-white/85 backdrop-blur-xl shadow-soft border-b border-ink-100'
            : 'bg-white/60 backdrop-blur-md',
        )}
        role="banner"
      >
        <div className="container-edge h-16 lg:h-20 flex items-center gap-4">
          <Link href="/" className="flex items-center" aria-label="بعثت مردم — صفحه اصلی">
            <Logo size={40} />
          </Link>

          {/* Desktop nav */}
          <nav className="hidden lg:flex items-center gap-1 mx-auto" aria-label="ناوبری اصلی">
            {primaryNav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="px-3 py-2 text-[15px] font-medium text-ink-700 rounded-lg
                           hover:text-brand-600 hover:bg-brand-50 transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>

          {/* Actions */}
          <div className="flex items-center gap-2 mr-auto">
            <button
              type="button"
              aria-label="جست‌وجو"
              className="hidden sm:inline-flex w-10 h-10 items-center justify-center rounded-full
                         text-ink-600 hover:bg-ink-100 transition-colors"
            >
              <Search className="w-5 h-5" />
            </button>
            <Link
              href="/notifications"
              aria-label="اعلان‌ها"
              className="hidden sm:inline-flex w-10 h-10 items-center justify-center rounded-full
                         text-ink-600 hover:bg-ink-100 transition-colors relative"
            >
              <Bell className="w-5 h-5" />
              <span className="absolute top-2 left-2 w-2 h-2 rounded-full bg-accent-500" />
            </Link>
            <Link href="/auth/login" className="btn-primary btn-sm hidden sm:inline-flex">
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

      {/* Spacer for fixed header */}
      <div aria-hidden="true" className="h-16 lg:h-20" />

      {/* Mobile sheet */}
      <div
        className={cn(
          'fixed inset-0 z-40 lg:hidden transition-opacity duration-300',
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
            'transition-transform duration-300 ease-out',
            open ? 'translate-x-0' : 'translate-x-full',
          )}
        >
          <div className="h-16 flex items-center justify-between px-4 border-b border-ink-100">
            <Logo size={36} />
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="w-10 h-10 inline-flex items-center justify-center rounded-lg hover:bg-ink-100"
              aria-label="بستن"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <nav className="p-4 flex flex-col gap-1" aria-label="ناوبری موبایل">
            {primaryNav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="px-4 py-3 rounded-xl text-ink-800 hover:bg-brand-50 hover:text-brand-700
                           font-medium transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="p-4 mt-2 border-t border-ink-100 flex flex-col gap-2">
            <Link href="/auth/login" className="btn-primary btn-md w-full">
              <LogIn className="w-4 h-4" /> ورود / ثبت‌نام
            </Link>
            <Link href="/support" className="btn-outline btn-md w-full">پشتیبانی</Link>
          </div>
        </aside>
      </div>
    </>
  );
}
