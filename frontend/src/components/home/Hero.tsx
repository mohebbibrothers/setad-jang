'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { ArrowLeft, Search, Sparkles, Flag } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';

/**
 * Hero section — top of homepage.
 * - Brand-forward, motion-rich but reduced-motion safe.
 * - Includes site-wide search inviting users straight into content.
 */
export function Hero() {
  return (
    <section className="relative overflow-hidden bg-gradient-to-bl from-brand-50 via-white to-accent-50/30">
      {/* Decorative shapes */}
      <div aria-hidden className="absolute inset-0 bg-grid-pattern opacity-[0.5]" />
      <motion.div
        aria-hidden
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, ease: 'easeOut' }}
        className="absolute -top-32 -left-32 w-[520px] h-[520px] rounded-full
                   bg-gradient-to-br from-brand-200/50 to-brand-500/10 blur-3xl"
      />
      <motion.div
        aria-hidden
        initial={{ opacity: 0, scale: 0.6 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, delay: 0.2, ease: 'easeOut' }}
        className="absolute -bottom-32 -right-20 w-[420px] h-[420px] rounded-full
                   bg-gradient-to-tr from-accent-300/40 to-accent-500/10 blur-3xl"
      />

      <div className="relative container-edge pt-12 pb-20 lg:pt-20 lg:pb-28">
        <div className="grid lg:grid-cols-12 gap-12 items-center">
          {/* Copy */}
          <div className="lg:col-span-7 text-center lg:text-right">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                         bg-white shadow-soft border border-brand-100"
            >
              <span className="relative flex w-2.5 h-2.5">
                <span className="absolute inset-0 rounded-full bg-brand-500 animate-pulse-ring" />
                <span className="relative w-2.5 h-2.5 rounded-full bg-brand-500" />
              </span>
              <span className="text-sm font-semibold text-brand-700">
                سامانه رسمی بعثت مردم — نسخه ۱
              </span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.15] text-ink-900"
            >
              با هم،{' '}
              <span className="text-gradient-brand">جهاد تبیین</span>
              <br className="hidden sm:block" />
              می‌سازیم؛ با هم، یاری می‌کنیم.
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="mt-6 text-lg leading-9 text-ink-600 max-w-2xl mx-auto lg:mx-0"
            >
              بعثت مردم پلتفرمی است یکپارچه برای{' '}
              <strong className="text-ink-800">مددکاری</strong>،{' '}
              <strong className="text-ink-800">آموزش</strong>،{' '}
              <strong className="text-ink-800">دیوار مهربانی</strong>،{' '}
              <strong className="text-ink-800">گزارش‌های مردمی</strong> و{' '}
              <strong className="text-ink-800">جایزه عدالت</strong>؛
              تا صدای مردم، عمل مردم شود.
            </motion.p>

            {/* Search */}
            <motion.form
              role="search"
              action="/search"
              method="get"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="mt-8 mx-auto lg:mx-0 max-w-2xl flex items-center bg-white rounded-2xl
                         shadow-card border border-ink-100 p-1.5 focus-within:ring-2 focus-within:ring-brand-500/50"
            >
              <div className="pr-4 pl-2 text-ink-400">
                <Search className="w-5 h-5" />
              </div>
              <input
                type="search"
                name="q"
                placeholder="در کمپین‌ها، دوره‌ها، گزارش‌ها و محتوای تبیینی جست‌وجو کنید…"
                className="flex-1 h-12 bg-transparent outline-none text-[15px]
                           placeholder:text-ink-400 text-ink-900"
                aria-label="جست‌وجو در سایت"
              />
              <button type="submit" className="btn-primary btn-md">
                جست‌وجو
              </button>
            </motion.form>

            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="mt-6 flex flex-wrap justify-center lg:justify-start gap-3"
            >
              <Link href="/madadkar" className="btn-accent btn-lg group">
                <Sparkles className="w-5 h-5" />
                مشارکت در کمپین‌ها
                <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
              </Link>
              <Link href="/public-reports/new" className="btn-outline btn-lg">
                <Flag className="w-5 h-5" />
                ثبت گزارش مردمی
              </Link>
            </motion.div>

            {/* Stats strip */}
            <motion.dl
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.5 }}
              className="mt-10 grid grid-cols-3 max-w-xl mx-auto lg:mx-0 divide-x divide-x-reverse divide-ink-200/70"
            >
              {[
                { v: '+۱۲٬۰۰۰', l: 'مشارکت‌کننده' },
                { v: '+۲٬۴۰۰', l: 'گزارش بررسی‌شده' },
                { v: '+۸۵۰', l: 'محتوای تبیینی' },
              ].map((s) => (
                <div key={s.l} className="px-4 text-center">
                  <dt className="text-2xl font-extrabold text-ink-900 tabular-nums">{s.v}</dt>
                  <dd className="mt-1 text-sm text-ink-500">{s.l}</dd>
                </div>
              ))}
            </motion.dl>
          </div>

          {/* Visual */}
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: 'easeOut' }}
            className="lg:col-span-5 relative"
          >
            <div className="relative aspect-square max-w-[480px] mx-auto">
              {/* Soft glow */}
              <div className="absolute inset-6 rounded-full bg-gradient-to-br from-brand-200 to-accent-200 blur-2xl opacity-60" />
              {/* Card */}
              <div className="relative h-full rounded-[2.5rem] bg-white shadow-float border border-ink-100
                              flex items-center justify-center overflow-hidden">
                <div className="absolute inset-0 bg-grid-pattern opacity-30" />
                <div className="relative scale-[2.4] origin-center animate-float">
                  <Logo size={120} withWordmark={false} />
                </div>
                <div className="absolute bottom-4 inset-x-4 rounded-2xl bg-white/85 backdrop-blur
                                border border-ink-100 p-4 flex items-center gap-3 shadow-soft">
                  <div className="w-10 h-10 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center">
                    <Sparkles className="w-5 h-5" />
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-ink-900">پلتفرم مردمی، یکپارچه</p>
                    <p className="text-xs text-ink-500">امن، شفاف، قابل اعتماد</p>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
