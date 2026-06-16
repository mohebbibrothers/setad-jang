'use client';

import Image from 'next/image';
import { Search } from 'lucide-react';
import { motion } from 'framer-motion';

/**
 * Hero — matches designer's layout 1:1
 * Centered: defenders cutout PNG with reflection-floor, decorative dotted curves
 * behind it, and a large pill-shaped search bar overlapping the bottom.
 */
export function Hero() {
  return (
    <section className="relative bg-white overflow-hidden">
      {/* Decorative dotted curves (designer asset) — mirrored on left & right */}
      <Image
        src="/brand/wave-dotted-1.png"
        alt=""
        width={470} height={254}
        aria-hidden="true"
        className="absolute top-12 -right-10 md:right-0 w-[320px] md:w-[440px] opacity-90 select-none pointer-events-none"
      />
      <Image
        src="/brand/wave-dotted-2.png"
        alt=""
        width={487} height={107}
        aria-hidden="true"
        className="absolute bottom-32 -left-10 md:left-0 w-[300px] md:w-[440px] opacity-80 select-none pointer-events-none scale-x-[-1]"
      />

      <div className="container-edge relative pt-8 md:pt-12 pb-0">
        {/* Defenders image — centered, with reflection effect */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          className="relative mx-auto w-full max-w-[680px]"
        >
          <Image
            src="/brand/hero-defenders.png"
            alt="مدافعان وطن — بعثت مردم"
            width={1348}
            height={1008}
            priority
            sizes="(max-width: 768px) 90vw, 680px"
            className="relative z-10 w-full h-auto select-none"
          />
          {/* Floor reflection */}
          <div
            aria-hidden="true"
            className="absolute inset-x-0 -bottom-2 h-32 z-0 pointer-events-none
                       bg-[radial-gradient(ellipse_at_center,rgba(13,128,116,0.10),transparent_70%)]"
          />
        </motion.div>

        {/* Search bar overlapping bottom of hero */}
        <motion.form
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          role="search"
          action="/search"
          method="get"
          className="relative z-20 mx-auto -mt-6 md:-mt-10 max-w-3xl
                     bg-white border border-ink-100 rounded-full shadow-card
                     flex items-center pl-2 pr-4 sm:pr-6 py-2 sm:py-2.5
                     focus-within:shadow-float focus-within:border-brand-300 transition-all"
        >
          <Search className="w-5 h-5 text-brand-500 shrink-0" aria-hidden="true" />
          <input
            type="search"
            name="q"
            placeholder="جست‌وجو در حرکت‌ها، آموزش‌ها، چالش‌ها و مشاغل"
            aria-label="جست‌وجو در سایت"
            className="flex-1 mx-3 sm:mx-4 h-10 sm:h-11 bg-transparent outline-none text-[14px] sm:text-[15px]
                       text-ink-900 placeholder:text-ink-400"
          />
          <button
            type="submit"
            className="hidden sm:inline-flex items-center justify-center h-10 px-5 rounded-full
                       bg-brand-500 text-white text-sm font-semibold hover:bg-brand-600 transition-colors"
          >
            جست‌وجو
          </button>
          <button
            type="submit"
            aria-label="جست‌وجو"
            className="sm:hidden w-10 h-10 inline-flex items-center justify-center rounded-full bg-brand-500 text-white"
          >
            <Search className="w-4 h-4" />
          </button>
        </motion.form>
      </div>
    </section>
  );
}
