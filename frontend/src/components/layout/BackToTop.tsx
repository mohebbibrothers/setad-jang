'use client';

import { useState, useEffect } from 'react';

/**
 * Back-to-top pill — bulletproof scroll-to-top.
 *
 * Why this is non-trivial:
 *   • `window.scrollTo({top: 0, behavior: 'smooth'})` works on most
 *     browsers BUT silently no-ops when CSS `html { scroll-behavior:
 *     smooth }` is combined with certain Safari versions, or when the
 *     scroll container is on a parent element (not the document root).
 *   • Different browsers scroll either `documentElement` or `body`;
 *     some respect both, some only one. We hit BOTH explicitly.
 *   • If `prefers-reduced-motion: reduce` is honoured by the user, the
 *     smooth animation is skipped — we fall back to an instant jump.
 *
 * Bonus polish: the pill only fades in once the user has scrolled
 * meaningfully (>= 320 px). This keeps the footer clean at the top of
 * the page where the button would be redundant.
 */
export function BackToTop() {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const onScroll = () => {
      setVisible((window.scrollY || document.documentElement.scrollTop || 0) > 320);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollToTop = () => {
    if (typeof window === 'undefined') return;
    const reduced =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
        : false;
    const behavior: ScrollBehavior = reduced ? 'auto' : 'smooth';

    // Hit every scroll surface — different browsers honour different ones.
    try { window.scrollTo({ top: 0, left: 0, behavior }); } catch { /* old browsers */ }
    if (document.scrollingElement) {
      try {
        document.scrollingElement.scrollTo({ top: 0, left: 0, behavior });
      } catch {
        document.scrollingElement.scrollTop = 0;
      }
    }
    if (document.documentElement) document.documentElement.scrollTop = 0;
    if (document.body)            document.body.scrollTop = 0;
  };

  return (
    <div
      className={`relative mt-7 flex justify-center transition-opacity duration-300
                  ${visible ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
    >
      <button
        type="button"
        onClick={scrollToTop}
        aria-label="بازگشت به ابتدای صفحه"
        className="group inline-flex items-center gap-2 text-[12px] font-extrabold text-ink-500
                   hover:text-brand-700 transition-colors bg-transparent border-0 cursor-pointer
                   font-[inherit] focus:outline-none focus-visible:text-brand-700"
      >
        <span
          className="w-7 h-7 rounded-full bg-white border border-ink-200
                     flex items-center justify-center
                     shadow-[0_2px_6px_-3px_rgba(15,20,32,.10)]
                     transition-all duration-200
                     group-hover:border-brand-300 group-hover:-translate-y-0.5
                     group-hover:shadow-[0_6px_12px_-4px_rgba(13,128,116,.30)]"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="18 15 12 9 6 15" />
          </svg>
        </span>
        بازگشت به بالا
      </button>
    </div>
  );
}
