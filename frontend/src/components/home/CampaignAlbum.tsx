'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence, type PanInfo } from 'framer-motion';
import Image from 'next/image';
import { formatPersianNumber } from '@/lib/utils';

/**
 * ─────────────────────────────────────────────────────────────────────────
 * Campaign Album — premium lightbox / gallery viewer.
 *
 * Backend contract (apps/madadkar):
 *   GET /api/v1/madadkar/campaigns/<slug>/  → CampaignPublicDetailSerializer
 *     {
 *       ...,
 *       cover_image: str,
 *       gallery_images: [
 *         { id, image, alt_text, display_order, created_at }, ...
 *       ]
 *     }
 *
 *   Source ordering:
 *     1. cover_image (always position 0)
 *     2. gallery_images sorted by `display_order` ASC (the backend already
 *        does this via `Meta.ordering = ["display_order", "created_at"]`)
 *
 *   The album surface here does NOT call the API itself — it receives a
 *   pre-built `images[]` array from the page that already has the cover
 *   prepended. The Section component is responsible for fetching the
 *   detail endpoint on-demand if a card was rendered from the LIST
 *   endpoint (which does NOT include gallery_images).
 *
 * UX:
 *   - Backdrop blur + dim + click-out close.
 *   - Concentric corners: outer card r=28, inner image r=20.
 *   - Keyboard: ←/→ to navigate, Esc to close.
 *   - Touch: horizontal swipe (Framer Motion drag) to navigate.
 *   - A horizontally-scrollable filmstrip of thumbnails anchored to the
 *     bottom of the panel; the active thumb gets a brand ring + scale up.
 *   - RTL-correct nav: "previous" button sits on the RTL-right because the
 *     reading direction is right-to-left.
 *   - A11y: role=dialog, aria-modal, focus-trap-light (body scroll lock),
 *     aria-label on every button, aria-live counter.
 * ─────────────────────────────────────────────────────────────────────────
 */

export type AlbumImage = {
  url: string;
  alt?: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  sponsor?: string;
  images: AlbumImage[];
  /** If we are still fetching the gallery from the detail endpoint. */
  loading?: boolean;
  /** Optional starting index — defaults to 0 (the cover). */
  startIndex?: number;
};

export function CampaignAlbum({
  open, onClose, title, sponsor, images, loading = false, startIndex = 0,
}: Props) {
  const [index, setIndex] = useState(startIndex);
  const total = images.length;
  const stripRef = useRef<HTMLDivElement>(null);

  // Reset index when the album opens for a new campaign.
  useEffect(() => { if (open) setIndex(Math.min(startIndex, Math.max(0, total - 1))); },
            [open, startIndex, total]);

  // Keep the active thumbnail visible inside the filmstrip.
  useEffect(() => {
    if (!open) return;
    const el = stripRef.current?.querySelector<HTMLElement>(`[data-thumb="${index}"]`);
    el?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [open, index]);

  const next = useCallback(
    () => setIndex((i) => (total ? (i + 1) % total : 0)),
    [total],
  );
  const prev = useCallback(
    () => setIndex((i) => (total ? (i - 1 + total) % total : 0)),
    [total],
  );

  // Keyboard navigation + body scroll lock + Esc close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      // ↓ Swap direction for RTL: ArrowRight = visually-right = "previous"
      //   in left-to-right reading, but the user reads right-to-left here
      //   so we map ArrowLeft → next and ArrowRight → prev.
      else if (e.key === 'ArrowLeft')  next();
      else if (e.key === 'ArrowRight') prev();
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose, next, prev]);

  const onDragEnd = (_: unknown, info: PanInfo) => {
    const dx = info.offset.x;
    const vx = info.velocity.x;
    if (dx > 70 || vx > 500)        prev();   // drag-right → previous (RTL)
    else if (dx < -70 || vx < -500) next();   // drag-left  → next     (RTL)
  };

  const current = images[index];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="album-root"
          role="dialog"
          aria-modal="true"
          aria-label={`گالری تصاویر — ${title}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[110] flex items-center justify-center
                     bg-ink-900/80 backdrop-blur-md p-3 sm:p-6"
          onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 16 }}
            animate={{ opacity: 1, scale: 1,    y: 0  }}
            exit   ={{ opacity: 0, scale: 0.96, y: 10 }}
            transition={{ type: 'spring', stiffness: 320, damping: 28 }}
            className="relative w-full max-w-[1024px] max-h-[92vh]
                       bg-white rounded-[28px] overflow-hidden flex flex-col
                       shadow-[0_40px_80px_-20px_rgba(0,0,0,.55)]"
          >
            {/* ── Header ───────────────────────────────────────────────── */}
            <div className="flex items-center justify-between gap-3 px-5 md:px-6 py-4
                            bg-gradient-to-l from-brand-50 via-white to-brand-50
                            border-b border-ink-100">
              <div className="flex items-center gap-3 min-w-0">
                <span className="shrink-0 inline-flex w-10 h-10 rounded-xl
                                 bg-gradient-to-br from-brand-500 to-brand-700 text-white
                                 items-center justify-center
                                 shadow-[0_8px_18px_-6px_rgba(13,128,116,.55)]">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="2.1" strokeLinecap="round"
                       strokeLinejoin="round" aria-hidden="true">
                    <rect x="3" y="3" width="18" height="18" rx="3" />
                    <circle cx="9" cy="9" r="2" />
                    <path d="m21 15-5-5L5 21" />
                  </svg>
                </span>
                <div className="min-w-0">
                  <h3 className="text-[14.5px] md:text-[15.5px] font-extrabold text-ink-900 leading-6 truncate">
                    {title}
                  </h3>
                  {sponsor && (
                    <p className="text-[12px] text-ink-500 font-medium leading-5 truncate">
                      مددکار: {sponsor}
                    </p>
                  )}
                </div>
              </div>

              {/* Counter + close */}
              <div className="flex items-center gap-2 shrink-0">
                <span
                  aria-live="polite"
                  className="hidden sm:inline-flex items-center px-3 h-8 rounded-full
                             bg-ink-50 text-ink-700 text-[12px] font-extrabold tabular-nums"
                >
                  {total ? `${formatPersianNumber(index + 1)} / ${formatPersianNumber(total)}` : '۰'}
                </span>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="بستن"
                  className="w-9 h-9 rounded-full bg-ink-50 text-ink-700 hover:bg-rose-500
                             hover:text-white flex items-center justify-center
                             transition-colors duration-200"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                       strokeLinejoin="round" aria-hidden="true">
                    <line x1="18" y1="6"  x2="6"  y2="18" />
                    <line x1="6"  y1="6"  x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>

            {/* ── Stage ────────────────────────────────────────────────── */}
            <div className="relative flex-1 bg-ink-900 overflow-hidden">
              {loading ? (
                <div className="absolute inset-0 flex items-center justify-center text-white/80">
                  <svg className="w-8 h-8 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
                    <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                </div>
              ) : total === 0 ? (
                <div className="absolute inset-0 flex items-center justify-center text-white/80 text-[13px] font-medium">
                  تصویری برای نمایش وجود ندارد.
                </div>
              ) : (
                <>
                  {/* Stage image — draggable for swipe navigation */}
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, scale: 0.98 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.99 }}
                      transition={{ duration: 0.25 }}
                      drag="x"
                      dragConstraints={{ left: 0, right: 0 }}
                      dragElastic={0.18}
                      onDragEnd={onDragEnd}
                      className="absolute inset-0 cursor-grab active:cursor-grabbing select-none"
                    >
                      {current?.url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={current.url}
                          alt={current.alt || title}
                          draggable={false}
                          className="absolute inset-0 w-full h-full object-contain
                                     [pointer-events:none]"
                        />
                      ) : null}
                    </motion.div>
                  </AnimatePresence>

                  {/* Edge controls — RTL-correct (prev on the right) */}
                  {total > 1 && (
                    <>
                      <button
                        type="button"
                        onClick={prev}
                        aria-label="تصویر قبلی"
                        className="absolute top-1/2 right-3 sm:right-5 -translate-y-1/2 z-10
                                   w-11 h-11 rounded-full bg-white/90 text-ink-800
                                   hover:bg-white hover:scale-105 active:scale-95
                                   flex items-center justify-center
                                   shadow-[0_10px_24px_-6px_rgba(0,0,0,.45)]
                                   transition-all duration-200"
                      >
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <polyline points="9 6 15 12 9 18" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        onClick={next}
                        aria-label="تصویر بعدی"
                        className="absolute top-1/2 left-3 sm:left-5 -translate-y-1/2 z-10
                                   w-11 h-11 rounded-full bg-white/90 text-ink-800
                                   hover:bg-white hover:scale-105 active:scale-95
                                   flex items-center justify-center
                                   shadow-[0_10px_24px_-6px_rgba(0,0,0,.45)]
                                   transition-all duration-200"
                      >
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                             strokeLinejoin="round" aria-hidden="true">
                          <polyline points="15 18 9 12 15 6" />
                        </svg>
                      </button>
                    </>
                  )}

                  {/* Counter chip — mobile */}
                  <span
                    className="sm:hidden absolute top-3 right-1/2 translate-x-1/2 z-10
                               inline-flex items-center px-3 h-7 rounded-full
                               bg-black/55 text-white text-[11.5px] font-extrabold tabular-nums
                               backdrop-blur-sm"
                  >
                    {`${formatPersianNumber(index + 1)} / ${formatPersianNumber(total)}`}
                  </span>
                </>
              )}
            </div>

            {/* ── Filmstrip ────────────────────────────────────────────── */}
            {total > 1 && !loading && (
              <div className="bg-white border-t border-ink-100 px-3 md:px-4 py-3">
                <div
                  ref={stripRef}
                  className="flex gap-2 overflow-x-auto pb-1 no-scrollbar"
                  style={{ scrollbarWidth: 'none' }}
                >
                  {images.map((img, i) => {
                    const active = i === index;
                    return (
                      <button
                        type="button"
                        key={`${img.url}-${i}`}
                        data-thumb={i}
                        onClick={() => setIndex(i)}
                        aria-label={`نمایش تصویر ${formatPersianNumber(i + 1)}`}
                        aria-current={active}
                        className={`relative shrink-0 rounded-[14px] overflow-hidden
                                    transition-all duration-200
                                    ${active
                                      ? 'ring-2 ring-brand-500 scale-[1.04] shadow-[0_10px_22px_-6px_rgba(13,128,116,.40)]'
                                      : 'ring-1 ring-ink-200 hover:ring-brand-300 hover:scale-[1.03] opacity-80 hover:opacity-100'}`}
                        style={{ width: 76, height: 76 }}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={img.url}
                          alt={img.alt || `تصویر ${i + 1}`}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                        {active && (
                          <span
                            className="absolute inset-0 ring-2 ring-inset ring-white/70 rounded-[14px]"
                            aria-hidden="true"
                          />
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Hide native scrollbars on the filmstrip in webkit & firefox.
// (Tailwind helper class injected globally; no-op if the project already
// exposes it — duplicates are harmless.)
declare global { /* eslint-disable @typescript-eslint/no-empty-object-type */ interface CSSStyleDeclaration {} }

/* The class .no-scrollbar is defined in globals.css; if it doesn't exist
   yet, the filmstrip simply shows a thin native scrollbar — graceful. */

// Re-export Image to keep tree-shaking honest if a parent imports * from here.
export { Image };
