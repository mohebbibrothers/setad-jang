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
 *
 * ────────────────────────────────────────────────────────────────────────
 *  IMPORTANT — overflow architecture
 *  The outer <section> is INTENTIONALLY NOT `overflow-hidden`. Earlier
 *  revisions clipped the section to hide the wave PNGs poking out past
 *  the viewport edges, but that also clipped the GlobalSearch dropdown
 *  panel (which overflows downward into the ActivitiesPanel area).
 *  Instead, decorations live inside a dedicated `.hero-deco-clip` div
 *  that has its OWN overflow-hidden — keeping the dropdown free to grow
 *  below the photo without being cut off.
 * ──────────────────────────────────────────────────────────────────────── */
export function Hero() {
  return (
    <section className="relative bg-white pt-6 md:pt-8 pb-0">
      {/* Decorative dotted curves clipped to the section width, OUTSIDE the
          search bar's z-stack — so the dropdown can extend downward into
          the next section unimpeded. */}
      <div
        aria-hidden="true"
        className="hero-deco-clip absolute inset-0 overflow-hidden pointer-events-none z-0"
      >
        <Image
          src="/brand/wave-dotted-1.png"
          alt=""
          width={470} height={254}
          priority
          className="absolute top-10 -right-4 md:right-[2%] w-[280px] md:w-[420px] opacity-95 select-none"
        />
        <Image
          src="/brand/wave-dotted-2.png"
          alt=""
          width={487} height={107}
          className="absolute bottom-28 -left-4 md:left-[2%] w-[260px] md:w-[420px] opacity-85 select-none scale-x-[-1]"
        />
      </div>

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

        {/* Production-grade omni-search. Mounted in its own motion wrapper
            so we can animate it in, while keeping the GlobalSearch root
            free of transforms (which would create a new stacking context
            and let parent overflow clip the dropdown). */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="relative z-[60]"
        >
          <GlobalSearch variant="hero" />
        </motion.div>
      </div>
    </section>
  );
}
