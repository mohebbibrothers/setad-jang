'use client';

import Image from 'next/image';
import { motion } from 'framer-motion';
import { GlobalSearch } from './GlobalSearch';

/**
 * Hero — matches designer 1:1.
 * Centered defenders cutout, dotted-wave decorations mirrored,
 * with the production-grade GlobalSearch pill overlapping the bottom
 * edge. The search bar is wired to every public DRF endpoint via
 * `lib/global-search.ts` and renders a rich suggestions panel with
 * keyboard navigation, recents, trending, and a ⌘K/Ctrl+K hotkey.
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

        {/* Production-grade omni-search — every public app is queried in
            parallel; results group by source with keyboard navigation,
            recents, trending, and a ⌘K hotkey. See GlobalSearch.tsx. */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          <GlobalSearch variant="hero" />
        </motion.div>
      </div>
    </section>
  );
}
