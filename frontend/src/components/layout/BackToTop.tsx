'use client';

/**
 * Back-to-top pill — tiny, polished ergonomics.
 *
 * The previous implementation was a plain <a href="#main"> which relied
 * on the browser jumping to the element with id="main". Two failure
 * modes were possible:
 *   1. The hash is already #main (e.g. user clicked it once already) →
 *      most browsers skip the scroll.
 *   2. The scroll target sits at the very top, which means the page is
 *      effectively already at offset 0 — the smooth-scroll never fires.
 *
 * This client island uses window.scrollTo({top: 0, behavior: 'smooth'})
 * explicitly so the behaviour is consistent on every browser, every
 * page state, every viewport.
 */
export function BackToTop() {
  return (
    <div className="relative mt-7 flex justify-center">
      <button
        type="button"
        onClick={() => {
          if (typeof window === 'undefined') return;
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
        aria-label="بازگشت به ابتدای صفحه"
        className="group inline-flex items-center gap-2 text-[12px] font-extrabold text-ink-500
                   hover:text-brand-700 transition-colors bg-transparent border-0 cursor-pointer
                   font-[inherit]"
      >
        <span
          className="w-7 h-7 rounded-full bg-white border border-ink-200
                     flex items-center justify-center
                     shadow-[0_2px_6px_-3px_rgba(15,20,32,.10)]
                     transition-all duration-200
                     group-hover:border-brand-300 group-hover:-translate-y-0.5"
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
