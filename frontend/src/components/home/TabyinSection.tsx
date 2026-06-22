'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';
import { EmptyState } from './EmptyState';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Tabyin (جهاد تبیین) section — designer-faithful (v2).
 *
 * Backend contract (apps/tabyin):
 *   GET /api/v1/tabyin/contents/        PublicTabyinContentListSerializer
 *     Query params (PublicTabyinContentFilter):
 *       - media_type ∈ {image, video, audio, other}
 *       - author     (icontains on author_username)
 *       - search     (FTS + trigram across title/description/author)
 *
 *   GET /api/v1/tabyin/contents/<external_id>/  detail
 *   POST /api/v1/tabyin/me/submissions/         user submission (auth-only)
 *
 * Public list serializer fields:
 *   external_id, title, description, author_username, origin,
 *   source_created_at, source_url, primary_media_type,
 *   attachments[]: { id, url, media_type, media_type_display, size,
 *                    duration, file_size, title, order }
 *
 * Designer brief (from the screenshot):
 *   - True 4-column masonry. Tiles have variable HEIGHT (some tall) —
 *     not a uniform grid; this mirrors a Pinterest/Behance feed and
 *     gives the wall its editorial character.
 *   - Most tiles are cover-only with a soft brand-teal tint overlay so
 *     every image reads as part of the same "Tabyin family", plus a
 *     bottom scrim so any overlaid title stays legible.
 *   - One tile in every fold is a 'quote' card — solid brand-green,
 *     white centred text with a quote glyph in the corner — used when
 *     the content is text-led (e.g. a manifesto excerpt).
 *   - Bottom-left of every tile carries two glass action chips:
 *       link (copy-share) + heart (bookmark).
 *   - 'بارگذاری بیشتر' mint pill below.
 *
 * UX upgrades (backend-driven, harmonised with the rest of the homepage):
 *   1. Top-left media-type badge for video / audio tiles (with the
 *      duration when ≥ 1s) — drawn from primary_media_type + duration.
 *      The image's the default, so it stays unbadged to keep the wall
 *      visually quiet.
 *   2. Plays-circle icon ALWAYS centred on video tiles, fading in on
 *      hover — turns any video into a one-click play affordance.
 *   3. Tiny 'مردمی' chip in the bottom-right when origin = user_submitted
 *      — gives social proof and rewards contributors.
 *   4. Filter strip (همه · تصویر · ویدئو · صوت) directly maps to the
 *      backend's media_type query param. Counts are live.
 *   5. The masonry layout is generated DETERMINISTICALLY from the item
 *      array so the same items always land in the same cells regardless
 *      of viewport — no jumping on resize.
 * ───────────────────────────────────────────────────────────────────────────
 */

export type TabyinItem = {
  id: string;
  slug: string;
  title?: string;
  summary?: string;
  coverUrl?: string;
  /** When variant='quote' the tile renders as a brand-green text card */
  variant?: 'cover' | 'quote';
  /** Optional masonry sizing hints (height multipliers) */
  tall?: boolean;          // span 2 rows on desktop
  /** Backend-driven extras */
  mediaType?: 'image' | 'video' | 'audio' | 'other';
  durationSeconds?: number;
  origin?: 'external' | 'user_submitted';
  authorName?: string;
  /** Original publisher URL (e.g. Telegram channel post) — surfaces an
   *  'منبع اصلی' affordance on the tile when present. */
  sourceUrl?: string;
  toneFrom?: string;
  toneTo?: string;
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Icons                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

function QuoteIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M7.17 6C4.31 6 2 8.31 2 11.17v6.66h6.66v-6.66H5c0-1.84 1.49-3.33 3.33-3.33V6H7.17zm10 0c-2.86 0-5.17 2.31-5.17 5.17v6.66h6.66v-6.66H15c0-1.84 1.49-3.33 3.33-3.33V6h-1.16z" />
    </svg>
  );
}

function PlayIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function VideoIcon({ className = 'w-3 h-3' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m22 8-6 4 6 4V8Z" />
      <rect x="2" y="6" width="14" height="12" rx="2" />
    </svg>
  );
}

function AudioIcon({ className = 'w-3 h-3' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M12 1a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3Z" />
      <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
      <line x1="12" y1="19" x2="12" y2="23" />
    </svg>
  );
}

function ImageIcon({ className = 'w-3 h-3' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-5-5L5 21" />
    </svg>
  );
}

function GridIcon({ className = 'w-3 h-3' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Helpers                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

function formatDuration(s?: number): string {
  if (!s || s <= 0) return '';
  if (s < 60) return `${s.toLocaleString('fa-IR')}″`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (r === 0) return `${m.toLocaleString('fa-IR')}:۰۰`;
  return `${m.toLocaleString('fa-IR')}:${r.toString().padStart(2, '0')}`;
}

const FILTERS = [
  { key: 'all',   label: 'همه',     Glyph: GridIcon  },
  { key: 'image', label: 'تصویر',   Glyph: ImageIcon },
  { key: 'video', label: 'ویدئو',   Glyph: VideoIcon },
  { key: 'audio', label: 'صوت',     Glyph: AudioIcon },
] as const;
type FilterKey = (typeof FILTERS)[number]['key'];

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function TabyinSection({ items }: { items: TabyinItem[] }) {
  const [filter, setFilter] = useState<FilterKey>('all');
  const [page, setPage]     = useState(0);

  const counts = useMemo(() => ({
    all:   items.length,
    image: items.filter((i) => (i.mediaType ?? 'image') === 'image').length,
    video: items.filter((i) => i.mediaType === 'video').length,
    audio: items.filter((i) => i.mediaType === 'audio').length,
  }), [items]);

  const filtered = useMemo(
    () => items.filter((i) => {
      if (filter === 'all') return true;
      return (i.mediaType ?? 'image') === filter;
    }),
    [items, filter],
  );

  // 10 tiles per page tile a perfect rectangle at EVERY breakpoint when the
  // tall pattern is exactly 2 tall + 8 short:
  //     tall × 2 + short × 8 = 4 + 8 = 12 row slots
  //     - Desktop (4 cols): 4 × 3 rows = 12 ✓
  //     - Tablet  (3 cols): 3 × 4 rows = 12 ✓
  //     - Mobile  (2 cols): 2 × 6 rows = 12 ✓
  // `grid-auto-flow: dense` packs the cells gap-free. Tall positions live
  // on the items themselves (see seed/loader) so every cover matches its
  // slot's aspect-ratio — the cover never gets cropped weirdly.
  const PAGE_SIZE = 10;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  const visible = useMemo(
    () => filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [filtered, page],
  );

  // Reset to first page when filter changes
  useEffect(() => { setPage(0); }, [filter]);

  // ── Sparse-mode detection ───────────────────────────────────────────
  // When the visible set is smaller than ONE full row at the current
  // viewport, we drop out of CSS grid into flex+wrap+justify-center so
  // orphan tiles centre instead of clinging to the RTL-right edge.
  const [cols, setCols] = useState(4);
  useEffect(() => {
    const measure = () => {
      const w = window.innerWidth;
      setCols(w >= 1024 ? 4 : w >= 768 ? 3 : 2);
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);
  const isSparse = visible.length > 0 && visible.length < cols;

  const goPrev = () => setPage((p) => (p - 1 + totalPages) % totalPages);
  const goNext = () => setPage((p) => (p + 1) % totalPages);

  return (
    <section className="section-y bg-white" id="tabyin">
      <div className="container-edge">
        <SectionTitle
          title="جهاد تبیین"
          description="در روزگارِ هیاهوی روایت‌ها، هر تصویر، هر ویدئو و هر سطر، یک تلاش برای رساندنِ صدای حقیقت است. اینجا دست‌به‌دست هم می‌دهیم تا روایتِ مردم گم نشود."
        />

        {/* Filter strip — media-type pills */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex p-1 bg-ink-50 rounded-full ring-1 ring-ink-100 shadow-inner"
               role="tablist" aria-label="نوع رسانه">
            {FILTERS.map((f) => {
              const isActive = filter === f.key;
              const c = counts[f.key];
              return (
                <button
                  key={f.key}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setFilter(f.key)}
                  className={`inline-flex items-center justify-center gap-1.5 h-10 px-3.5 sm:px-4
                              rounded-full text-[12.5px] font-extrabold whitespace-nowrap
                              transition-all duration-200
                              ${isActive
                                ? 'bg-gradient-to-l from-brand-500 to-brand-700 text-white shadow-[0_8px_20px_-6px_rgba(13,128,116,.55)]'
                                : 'text-ink-600 hover:text-ink-900 hover:bg-white/60'}`}
                >
                  <f.Glyph className="w-3.5 h-3.5" />
                  <span>{f.label}</span>
                  <span className={`inline-flex items-center justify-center min-w-[20px] h-5 px-1.5
                                    rounded-full text-[10.5px] font-extrabold tabular-nums
                                    ${isActive ? 'bg-white/25 text-white' : 'bg-ink-100 text-ink-500'}`}>
                    {c.toLocaleString('fa-IR')}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Fixed-area masonry: 4 cols × 4 rows on desktop, dense packing ── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={`${filter}-${page}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.28 }}
            className={
              isSparse
                ? 'flex flex-wrap justify-center items-start gap-3 md:gap-4'
                : 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 ' +
                  'auto-rows-[120px] sm:auto-rows-[140px] md:auto-rows-[160px] ' +
                  'gap-3 md:gap-4'
            }
            style={isSparse ? undefined : { gridAutoFlow: 'dense' }}
          >
            {visible.map((it, i) => {
              // ── PAGE-LOCAL tall pattern ─────────────────────────────
              // We need EXACTLY 2 tall + 8 short on every page so:
              //   tall(=2 slots) × 2 + short(=1 slot) × 8 = 12 slots
              //   - 4-col: 3 rows × 4 = 12 ✓
              //   - 3-col: 4 rows × 3 = 12 ✓
              //   - 2-col: 6 rows × 2 = 12 ✓
              // We place tall on slots 0 and 1 — the EARLIEST positions —
              // so `grid-auto-flow: dense` never has to spill a tall into
              // the bottom row, where it would push the grid past its
              // declared row count and visually escape the panel.
              const isLastPageAndShort =
                visible.length < PAGE_SIZE; // last page may have fewer items
              const tall = !isLastPageAndShort && (i === 0 || i === 1);
              return (
                <TabyinTile
                  key={it.id}
                  it={it}
                  index={i}
                  forceTall={tall}
                  sparse={isSparse}
                />
              );
            })}
            {visible.length === 0 && (
              <div className="col-span-full w-full">
                <EmptyState
                  title={items.length === 0
                    ? 'هنوز محتوایی منتشر نشده'
                    : 'محتوایی در این فیلتر یافت نشد'}
                  description={items.length === 0
                    ? 'به‌محض انتشار اولین روایت‌های جهاد تبیین، اینجا قابل مشاهده خواهد بود.'
                    : 'فیلتر دیگری را امتحان کن یا «همه» را انتخاب کن.'}
                  iconPath="m3 11 18-5v12L3 14v-3z M11.6 16.8a3 3 0 1 1-5.8-1.6"
                />
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        {/* Pager (brand PNG arrows — disabled when there's a single page) */}
        <div className="flex items-center justify-center gap-4 mt-8">
          <button
            type="button" aria-label="قبلی" onClick={goPrev} disabled={totalPages <= 1}
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200 disabled:opacity-40
                       disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            <Image src="/brand/pager-arrow-prev.png" alt="" fill sizes="48px" className="object-contain" />
          </button>
          <button
            type="button" aria-label="بعدی" onClick={goNext} disabled={totalPages <= 1}
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200 disabled:opacity-40
                       disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            <Image src="/brand/pager-arrow-next.png" alt="" fill sizes="48px" className="object-contain" />
          </button>
        </div>

        {/* CTAs below the pager:
            - 'مشاهده همه محتوا'  → secondary, brand-ghost (browsing intent)
            - 'افزودن محتوا'      → primary, mint pill (action intent,
              routes through the auth-required user-submission flow that
              maps to POST /api/v1/tabyin/me/submissions/)                */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-6">
          <Link
            href="/tabyin"
            className="inline-flex items-center gap-2 h-12 px-7 rounded-full
                       bg-white border-2 border-brand-500 text-brand-700 font-extrabold text-[14px]
                       hover:bg-brand-50 transition-colors"
          >
            <span>مشاهده همه محتوا</span>
            <Icon name="arrow-left" className="w-4 h-4" />
          </Link>
          <Link
            href="/tabyin/new"
            className="inline-flex items-center gap-2 h-12 px-7 rounded-full
                       bg-mint-500 hover:bg-mint-600 text-white font-extrabold text-[14px]
                       shadow-[0_8px_24px_-8px_rgba(37,197,186,.5)] transition-all
                       hover:scale-[1.02] active:scale-[.98]"
          >
            <Icon name="plus" className="w-4 h-4" strokeWidth={2.5} />
            <span>افزودن محتوا</span>
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Tile                                                                     */
/* ───────────────────────────────────────────────────────────────────────── */

function TabyinTile({
  it, index, forceTall = false, sparse = false,
}: {
  it: TabyinItem; index: number; forceTall?: boolean; sparse?: boolean;
}) {
  const isQuote = it.variant === 'quote';
  const isVideo = it.mediaType === 'video';
  const isAudio = it.mediaType === 'audio';
  const isUser  = it.origin === 'user_submitted';
  // `forceTall` is computed PAGE-LOCALLY in the section so the tall slots
  // always align to the dense grid and never overflow on the last row.
  // The data-driven `it.tall` is intentionally ignored here.
  // In SPARSE mode every tile is short (a single centred row).
  const tall    = !sparse && forceTall;

  // Width / height presets for sparse mode mirror each breakpoint's
  // column count so the visual rhythm stays identical to the dense grid.
  const sparseSizing = sparse
    ? 'w-[calc((100%-0.75rem)/2)] h-[120px] ' +
      'sm:h-[140px] ' +
      'md:w-[calc((100%-2*1rem)/3)] md:h-[160px] ' +
      'lg:w-[calc((100%-3*1rem)/4)] ' +
      'flex-none'
    : (tall ? 'row-span-2' : 'row-span-1');

  return (
    <motion.article
      initial={{ opacity: 0, scale: 0.96, y: 12 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.025, 0.35) }}
      className={`group relative rounded-2xl overflow-hidden isolate
                  shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                  hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.28)]
                  hover:-translate-y-1 transition-all duration-300
                  ${sparseSizing}`}
    >
      {isQuote ? (
        /* ── Quote tile (solid brand-green text card) ───────────────── */
        <Link
          href={`/tabyin/${it.slug}`}
          className="relative block w-full h-full p-4 md:p-5 text-white
                     flex items-center justify-center text-center
                     bg-gradient-to-br from-brand-400 via-brand-500 to-brand-700"
        >
          {/* Decorative quote glyph in the corner */}
          <QuoteIcon className="absolute top-3 right-3 w-6 h-6 opacity-25" />
          <QuoteIcon className="absolute bottom-3 left-3 w-5 h-5 opacity-15 rotate-180" />
          {/* Subtle dotted texture */}
          <div
            aria-hidden="true"
            className="absolute inset-0 opacity-[0.08] pointer-events-none"
            style={{
              backgroundImage:
                'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.85) 1px, transparent 1px)',
              backgroundSize: '14px 14px',
            }}
          />
          <p className="relative text-[12px] md:text-[13.5px] leading-7 font-bold drop-shadow">
            {it.summary}
          </p>
        </Link>
      ) : it.coverUrl ? (
        /* ── Cover tile (image) ─────────────────────────────────────── */
        <Link href={`/tabyin/${it.slug}`} className="relative block w-full h-full">
          <Image
            src={it.coverUrl}
            alt={it.title || 'محتوای تبیینی'}
            fill
            sizes="(max-width: 768px) 45vw, 22vw"
            className="object-cover transition-transform duration-500 group-hover:scale-105"
          />
          {/* Brand-teal duotone tint — unifies the wall */}
          <div aria-hidden="true"
               className="absolute inset-0 bg-gradient-to-br
                          from-brand-500/[0.12] via-transparent to-brand-900/[0.18]
                          mix-blend-multiply pointer-events-none" />
          {/* Bottom scrim for title legibility */}
          <div aria-hidden="true"
               className="absolute inset-x-0 bottom-0 h-3/5
                          bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
          {/* Title overlay (only when there's a title) */}
          {it.title && (
            <p className="absolute bottom-3 inset-x-3 text-white text-[12.5px] md:text-[13px]
                          font-extrabold leading-5 line-clamp-2 drop-shadow-[0_2px_6px_rgba(0,0,0,.6)]">
              {it.title}
            </p>
          )}
          {/* Center play affordance — only on video tiles, fades in on hover */}
          {isVideo && (
            <div aria-hidden="true"
                 className="absolute inset-0 flex items-center justify-center z-[4]
                            opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <span className="w-12 h-12 rounded-full bg-white/95 text-brand-600
                               flex items-center justify-center
                               shadow-[0_12px_28px_-8px_rgba(0,0,0,.55)]
                               scale-90 group-hover:scale-100 transition-transform duration-300">
                <PlayIcon className="w-5 h-5" />
              </span>
            </div>
          )}
        </Link>
      ) : (
        /* ── Fallback gradient tile ─────────────────────────────────── */
        <Link
          href={`/tabyin/${it.slug}`}
          className="block w-full h-full"
          style={{ background: `linear-gradient(135deg, ${it.toneFrom || '#0D8074'}, ${it.toneTo || '#053832'})` }}
        />
      )}

      {/* Media-type badge — top-left (only for non-image, non-quote) */}
      {!isQuote && (isVideo || isAudio) && (
        <span className="absolute top-2.5 left-2.5 z-10 inline-flex items-center gap-1
                         h-6 px-2 rounded-full bg-black/60 text-white
                         text-[10.5px] font-extrabold backdrop-blur-md
                         tabular-nums">
          {isVideo ? <VideoIcon className="w-3 h-3" /> : <AudioIcon className="w-3 h-3" />}
          {it.durationSeconds ? formatDuration(it.durationSeconds) : (isVideo ? 'ویدئو' : 'صوت')}
        </span>
      )}

      {/* 'مردمی' chip — when content was contributed by a user */}
      {!isQuote && isUser && (
        <span className="absolute top-2.5 right-2.5 z-10 inline-flex items-center gap-1
                         h-6 px-2 rounded-full bg-mint-500/95 text-white
                         text-[10.5px] font-extrabold backdrop-blur-md
                         shadow-[0_4px_12px_-4px_rgba(37,197,186,.55)]">
          <Icon name="sparkles" className="w-3 h-3" />
          مردمی
        </span>
      )}

      {/* Bottom-left action chips: link (copy) + heart (bookmark) */}
      <div className="absolute bottom-2.5 left-2.5 flex items-center gap-1.5 z-10">
        <button
          type="button"
          aria-label="کپی لینک"
          className="w-7 h-7 rounded-full bg-white/90 hover:bg-white text-ink-700
                     flex items-center justify-center backdrop-blur-md
                     shadow-[0_2px_6px_-2px_rgba(0,0,0,.25)]
                     hover:scale-110 transition-all duration-150"
        >
          <Icon name="link" className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          aria-label="افزودن به علاقه‌مندی‌ها"
          className="w-7 h-7 rounded-full bg-white/90 hover:bg-white text-ink-700
                     hover:text-rose-500 flex items-center justify-center backdrop-blur-md
                     shadow-[0_2px_6px_-2px_rgba(0,0,0,.25)]
                     hover:scale-110 transition-all duration-150"
        >
          <Icon name="heart" className="w-3.5 h-3.5" />
        </button>
      </div>
    </motion.article>
  );
}
