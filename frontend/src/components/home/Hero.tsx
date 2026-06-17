'use client';

import Image from 'next/image';
import { Search } from 'lucide-react';
import { motion } from 'framer-motion';

/**
 * Hero — matches designer 1:1.
 * Centered defenders cutout, dotted-wave decorations mirrored,
 * thin brand-coloured search pill overlapping the bottom edge with
 * a search-icon submit button (no text label).
 */
export function Hero() {
  return (
    <section className="relative bg-white overflow-hidden pt-6 md:pt-8 pb-0">
      {/* Decorative dotted curves (designer assets), mirrored each side */}
      <Image
        src="/brand/wave-dotted-1.png"
        alt=""
        width={470} height={254}
        aria-hidden="true"
        priority
        className="absolute top-10 -right-4 md:right-[2%] w-[280px] md:w-[420px] opacity-95 select-none pointer-events-none"
      />
      <Image
        src="/brand/wave-dotted-2.png"
        alt=""
        width={487} height={107}
        aria-hidden="true"
        className="absolute bottom-28 -left-4 md:left-[2%] w-[260px] md:w-[420px] opacity-85 select-none pointer-events-none scale-x-[-1]"
      />

      <div className="container-edge relative">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
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
          {/* White fade gradient at the bottom of the photo — matches mockup */}
          <div
            aria-hidden="true"
            className="absolute inset-x-0 bottom-0 h-[42%] z-20 pointer-events-none
                       bg-[linear-gradient(to_top,#ffffff_0%,rgba(255,255,255,0.92)_28%,rgba(255,255,255,0)_100%)]"
          />
        </motion.div>

        <motion.form
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          role="search"
          action="/search"
          method="get"
          className="relative z-30 mx-auto -mt-[100px] md:-mt-[120px] lg:-mt-[140px] max-w-3xl
                     bg-white border-[1.5px] border-brand-300 rounded-full
                     shadow-[0_14px_30px_-10px_rgba(11,53,48,0.25),0_4px_10px_-4px_rgba(11,53,48,0.10)]
                     flex items-center pl-1.5 pr-6 py-1.5
                     focus-within:border-brand-500 transition-all gap-2"
        >
          <input
            type="search"
            name="q"
            placeholder="جست‌وجو در حرکت‌ها، آموزش‌ها، چالش‌ها و مشاغل"
            aria-label="جست‌وجو در سایت"
            dir="rtl"
            className="flex-1 h-10 md:h-11 bg-transparent outline-none text-[14px] md:text-[15px]
                       text-ink-900 placeholder:text-ink-400 text-right"
          />
          <button
            type="submit"
            aria-label="جست‌وجو"
            className="w-10 h-10 md:w-11 md:h-11 rounded-full text-brand-500 hover:bg-brand-50
                       inline-flex items-center justify-center transition-colors shrink-0"
          >
            <Search className="w-5 h-5" strokeWidth={2.2} />
          </button>
        </motion.form>
      </div>
    </section>
  );
}
