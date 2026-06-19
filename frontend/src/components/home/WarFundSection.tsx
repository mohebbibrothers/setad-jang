'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { formatPersianNumber } from '@/lib/utils';
import { apiFetch } from '@/lib/api';
import { CampaignAlbum, type AlbumImage } from './CampaignAlbum';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * War-fund (Madadkar) campaign card — designer-faithful (v3).
 *
 * Backend contract (apps/madadkar):
 *   GET /api/v1/madadkar/campaigns/  → CampaignPublicListSerializer
 *
 * Fields used (mirror of serializers.CampaignPublicListSerializer.Meta.fields):
 *   id, sponsor{id,name,slug,logo}, title, slug, cover_image,
 *   total_amount, total_shares, share_price, purchased_shares,
 *   purchased_amount, participant_count, remaining_shares,
 *   progress_percent, is_fully_funded, status, status_display,
 *   has_deadline, deadline, published_at, completed_at, closed_at
 *
 * Layout (matches the designer's mockup exactly):
 *
 *   ┌──────────────────────────────────────────────────┐
 *   │  ┌──────────┐   ┌──────────────────────────┐    │
 *   │  │  cover   │   │       campaign title     │    │
 *   │  │ 130×130  │   ├──────────────────────────┤    │
 *   │  │          │   │   مبلغ کل ··· ۱۰،۰۰۰،۰۰۰،۰۰۰ ریال │
 *   │  └──────────┘   ├──────────┬───────────────┤    │
 *   │   ٪۵۰           │ باقی     │   تعداد       │    │
 *   │  ▓▓▓▓░░░░       ├──────────┴───────────────┤    │
 *   │                 │   مددکار ··· جهادی       │    │
 *   │                 └──────────────────────────┘    │
 *   │                                                  │
 *   │  ┌─────────── مدد به حرکت  ✋ ─────────────┐   │
 *   │  └──────────────────────────────────────────┘   │
 *   └──────────────────────────────────────────────────┘
 *
 *   - Cover sits on the RTL-right (DOM first inside .wf-body).
 *   - Percentage label and progress bar live UNDER the cover.
 *   - All meta-pill values are HORIZONTALLY CENTERED.
 *   - CTA icon (helping hand) is on the LTR-left = end-of-line in RTL.
 *
 * Display notes:
 *   - Backend stores monetary fields in TOMAN; the mockup shows RIAL.
 *     We multiply totalAmount × 10 at render time to match the design.
 * ───────────────────────────────────────────────────────────────────────────
 */
export type CampaignCard = {
  slug: string;
  title: string;
  sponsor: string;
  /** Toman (storage unit); UI multiplies by 10 to render Rial. */
  totalAmount: number;
  sharePrice: number;
  sharesTotal: number;
  sharesRemaining: number;
  progressPercent: number;
  coverUrl?: string;
  toneFrom?: string;
  toneTo?: string;
  /** Optional pre-loaded gallery (already sorted by display_order asc).
   *  When absent and the user opens the album, the section fetches
   *  /madadkar/campaigns/<slug>/ on-demand. */
  gallery?: AlbumImage[];
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Atoms                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

/** Meta pill — flex layout that GUARANTEES the label, value and unit
 *  never collide at any width.
 *
 *   ┌─────────────────────────────────────────────────────────┐
 *   │  label   │            number (centre, truncate)         │  unit │
 *   │ (shrink) │              flex-1 min-w-0                  │(shrink)│
 *   └─────────────────────────────────────────────────────────┘
 *
 *  Label and unit are flex-shrink:0, the number gets flex-1 + min-w-0 +
 *  truncate so when the pill is narrow the NUMBER shortens with an
 *  ellipsis — the label and the unit stay readable.
 *  At idle widths the number still reads visually centred because the
 *  label+unit have similar visual weight on each side.
 */
function MetaPill({
  label,
  value,
  unit,
  emphasis = 'num',
}: {
  label: string;
  value: string | number;
  unit?: string;
  emphasis?: 'num' | 'text';
}) {
  return (
    <div
      className="h-[40px] rounded-[10px] border border-ink-200 bg-white
                 flex items-center gap-1.5 px-3"
    >
      {/* Label — RTL-start (right) */}
      <span
        className="text-[12px] text-ink-500 font-medium leading-none
                   whitespace-nowrap shrink-0"
      >
        {label}
      </span>

      {/* Value — fills the remaining space, truncates if too long */}
      <span
        className={`flex-1 min-w-0 text-center
                    font-extrabold text-[13.5px] text-ink-900
                    whitespace-nowrap overflow-hidden text-ellipsis
                    ${emphasis === 'num' ? 'tabular-nums' : ''}`}
        title={typeof value === 'string' ? value : undefined}
      >
        {typeof value === 'number' ? formatPersianNumber(value) : value}
      </span>

      {/* Unit — LTR-start (left), only when provided */}
      {unit && (
        <span
          className="text-[11px] text-ink-400 font-medium leading-none
                     whitespace-nowrap shrink-0"
        >
          {unit}
        </span>
      )}
    </div>
  );
}

/** Helping-hand icon — matches the palm glyph on the mockup's CTA */
function HandIcon({ className = 'w-[18px] h-[18px]' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.1}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M18 11V6a2 2 0 0 0-4 0v5" />
      <path d="M14 10V4a2 2 0 0 0-4 0v6" />
      <path d="M10 10.5V6a2 2 0 0 0-4 0v8" />
      <path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.9-5.7-2.5L1.5 14a2 2 0 0 1 3-2.6L7 13" />
    </svg>
  );
}

/** Fallback cover: tasteful gradient + dotted texture + a centered small icon */
function CoverFallback({
  toneFrom = '#0D8074',
  toneTo = '#053832',
}: {
  toneFrom?: string;
  toneTo?: string;
}) {
  return (
    <div
      className="relative w-full h-full overflow-hidden"
      style={{ background: `linear-gradient(135deg, ${toneFrom}, ${toneTo})` }}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.18] pointer-events-none"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.85) 1px, transparent 1px)',
          backgroundSize: '8px 8px',
        }}
      />
      <HandIcon className="absolute inset-0 m-auto w-12 h-12 text-white/90" />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Card                                                                     */
/* ───────────────────────────────────────────────────────────────────────── */

function Card({
  c, delay = 0, onOpenAlbum,
}: {
  c: CampaignCard;
  delay?: number;
  onOpenAlbum: (c: CampaignCard) => void;
}) {
  // UI displays Rial; backend stores Toman → ×10 at render time.
  const totalRial = c.totalAmount * 10;
  const pct = Math.round(c.progressPercent);
  const galleryHint = (c.gallery?.length ?? (c.coverUrl ? 1 : 0));

  return (
    <motion.article
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.45, delay }}
      className="group bg-white rounded-[18px] border border-ink-100
                 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                 hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.22)]
                 hover:-translate-y-0.5 transition-all duration-300 overflow-hidden"
    >
      <div className="p-4 md:p-5">
        {/* ── Body: 2-column layout (cover on RTL-right, content on left) ── */}
        <div className="flex items-stretch gap-4">

          {/* Right column: cover + percent + progress (DOM-first = RTL-right) */}
          <div className="flex flex-col items-center shrink-0 w-[96px] sm:w-[110px] md:w-[130px]">
            <button
              type="button"
              onClick={() => onOpenAlbum(c)}
              aria-label={`نمایش آلبوم تصاویر ${c.title}`}
              className="relative w-full aspect-square rounded-[14px] overflow-hidden
                         ring-1 ring-ink-100 bg-ink-50 cursor-zoom-in
                         focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {c.coverUrl ? (
                <Image
                  src={c.coverUrl}
                  alt={c.title}
                  fill
                  sizes="(min-width: 768px) 130px, (min-width: 640px) 110px, 96px"
                  className="object-cover transition-transform duration-500 group-hover:scale-105"
                />
              ) : (
                <CoverFallback toneFrom={c.toneFrom} toneTo={c.toneTo} />
              )}

              {/* Album hint chip — bottom-left of the cover */}
              {galleryHint > 1 && (
                <span
                  className="absolute bottom-1.5 left-1.5 inline-flex items-center gap-1
                             px-1.5 h-5 rounded-md bg-black/55 backdrop-blur-sm
                             text-white text-[10px] font-extrabold tabular-nums
                             ring-1 ring-white/20"
                  aria-hidden="true"
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
                       stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                       strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="3" />
                    <circle cx="9" cy="9" r="2" />
                    <path d="m21 15-5-5L5 21" />
                  </svg>
                  {formatPersianNumber(galleryHint)}
                </span>
              )}

              {/* Hover veil + "view album" affordance */}
              <span
                className="absolute inset-0 bg-gradient-to-t from-black/55 via-transparent to-transparent
                           opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                aria-hidden="true"
              />
              <span
                className="absolute inset-x-0 bottom-1.5 text-center
                           text-white text-[10.5px] font-extrabold
                           opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                aria-hidden="true"
              >
                نمایش آلبوم
              </span>
            </button>

            {/* Percent — directly under the cover */}
            <div className="mt-2.5 text-[12px] font-extrabold text-ink-700 tabular-nums leading-none">
              ٪{formatPersianNumber(pct)}
            </div>

            {/* Progress bar — full cover-column width */}
            <div className="mt-1.5 w-full h-[6px] rounded-full bg-ink-100 overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                whileInView={{ width: `${pct}%` }}
                viewport={{ once: true }}
                transition={{ duration: 1.1, ease: 'easeOut' }}
                className="h-full rounded-full bg-gradient-to-l from-brand-400 to-brand-600"
              />
            </div>
          </div>

          {/* Left column: title + 3 meta pills */}
          <div className="flex-1 min-w-0 flex flex-col">
            <Link
              href={`/madadkar/${c.slug}`}
              className="font-extrabold text-[14.5px] md:text-[15px] text-ink-900 leading-7
                         line-clamp-2 hover:text-brand-600 transition-colors mb-3"
            >
              {c.title}
            </Link>

            <div className="space-y-2">
              <MetaPill label="مبلغ کل" value={totalRial} unit="ریال" />

              <div className="grid grid-cols-2 gap-2">
                <MetaPill label="باقی‌مانده" value={c.sharesRemaining} unit="سهم" />
                <MetaPill label="تعداد سهم" value={c.sharesTotal} unit="سهم" />
              </div>

              <MetaPill label="مددکار" value={c.sponsor} emphasis="text" />
            </div>
          </div>
        </div>

        {/* ── CTA: full-width, hand icon on the visual LEFT (end-of-line in RTL) ── */}
        <Link
          href={`/madadkar/${c.slug}/participate`}
          className="relative inline-flex items-center justify-center gap-2 w-full h-[46px] mt-4
                     rounded-[12px] bg-brand-500 hover:bg-brand-600 active:bg-brand-700
                     text-white text-[14.5px] font-extrabold
                     shadow-[0_6px_14px_-6px_rgba(13,128,116,.55)]
                     transition-colors overflow-hidden"
        >
          <span>مدد به حرکت</span>
          <HandIcon />
        </Link>
      </div>
    </motion.article>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

/** Shape of the campaign detail endpoint we care about for the album.
 *  Mirrors apps.madadkar.serializers.CampaignPublicDetailSerializer. */
type ApiCampaignDetail = {
  cover_image?: string | null;
  title?: string;
  gallery_images?: Array<{
    id: number;
    image: string;
    alt_text?: string;
    display_order?: number;
  }>;
};

export function WarFundSection({ campaigns }: { campaigns: CampaignCard[] }) {
  // 4 cards per page (2×2 on desktop); extra pages reached via the pager.
  const PAGE_SIZE = 4;
  const totalPages = Math.max(1, Math.ceil(campaigns.length / PAGE_SIZE));
  const [page, setPage] = useState(0);
  const visible = useMemo(
    () => campaigns.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [campaigns, page],
  );

  const prev = () => setPage((p) => (p - 1 + totalPages) % totalPages);
  const next = () => setPage((p) => (p + 1) % totalPages);

  // ─── Album state ──────────────────────────────────────────────────────
  const [album, setAlbum] = useState<{
    open: boolean;
    title: string;
    sponsor?: string;
    images: AlbumImage[];
    loading: boolean;
  }>({ open: false, title: '', images: [], loading: false });

  // In-memory cache so reopening the same album never re-fetches.
  const [galleryCache, setGalleryCache] = useState<Record<string, AlbumImage[]>>({});

  const closeAlbum = useCallback(() => {
    setAlbum((a) => ({ ...a, open: false }));
  }, []);

  const buildImages = useCallback(
    (c: CampaignCard, extra?: AlbumImage[]): AlbumImage[] => {
      const out: AlbumImage[] = [];
      if (c.coverUrl) out.push({ url: c.coverUrl, alt: c.title });
      if (extra && extra.length) {
        // De-duplicate against the cover (some backends repeat the cover
        // inside gallery_images by mistake).
        for (const im of extra) {
          if (!out.some((o) => o.url === im.url)) out.push(im);
        }
      }
      return out;
    },
    [],
  );

  const openAlbum = useCallback(async (c: CampaignCard) => {
    // 1. seed-supplied gallery → open immediately
    if (c.gallery && c.gallery.length) {
      setAlbum({
        open: true, title: c.title, sponsor: c.sponsor,
        images: buildImages(c, c.gallery), loading: false,
      });
      return;
    }
    // 2. cached → open immediately
    const cached = galleryCache[c.slug];
    if (cached) {
      setAlbum({
        open: true, title: c.title, sponsor: c.sponsor,
        images: buildImages(c, cached), loading: false,
      });
      return;
    }
    // 3. fetch from detail endpoint
    setAlbum({
      open: true, title: c.title, sponsor: c.sponsor,
      images: buildImages(c), loading: true,
    });
    try {
      const detail = await apiFetch<ApiCampaignDetail>(
        `/madadkar/campaigns/${encodeURIComponent(c.slug)}/`,
        { revalidate: 300, tags: [`campaign:${c.slug}`] },
      );
      const fetched: AlbumImage[] = (detail.gallery_images ?? [])
        .slice()
        .sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
        .map((g) => ({ url: g.image, alt: g.alt_text || c.title }));
      setGalleryCache((prev) => ({ ...prev, [c.slug]: fetched }));
      setAlbum((a) => a.open
        ? { ...a, images: buildImages(c, fetched), loading: false }
        : a);
    } catch {
      // Silent fallback — keep the cover-only album visible.
      setAlbum((a) => a.open ? { ...a, loading: false } : a);
    }
  }, [galleryCache, buildImages]);

  return (
    <section className="section-y bg-white" id="warfund">
      <div className="container-edge">
        <SectionTitle
          title="پشتیبانی مالی جنگ"
          description="کنار هر دست خالی، صدها دست یاری‌رسان ایستاده. هر سهمی که می‌خری، یک قدم نزدیک‌تر به آرامش مدافعان و خانواده‌هاست."
        />

        <AnimatePresence mode="wait">
          <motion.div
            key={page}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
            className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5"
          >
            {visible.map((c, i) => (
              <Card key={c.slug} c={c} delay={i * 0.06} onOpenAlbum={openAlbum} />
            ))}
          </motion.div>
        </AnimatePresence>

        {/* Pager — brand PNG arrows, real interactive paging */}
        <div className="flex items-center justify-center gap-4 mt-8">
          <button
            type="button"
            aria-label="قبلی"
            onClick={prev}
            disabled={totalPages <= 1}
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200 disabled:opacity-40
                       disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            <Image src="/brand/pager-arrow-prev.png" alt="" fill sizes="48px" className="object-contain" />
          </button>
          <button
            type="button"
            aria-label="بعدی"
            onClick={next}
            disabled={totalPages <= 1}
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200 disabled:opacity-40
                       disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            <Image src="/brand/pager-arrow-next.png" alt="" fill sizes="48px" className="object-contain" />
          </button>
        </div>

        <div className="flex justify-center mt-6">
          <Link
            href="/madadkar"
            className="inline-flex items-center gap-2 h-12 px-7 rounded-full
                       bg-white border-2 border-brand-500 text-brand-700 font-extrabold text-[14px]
                       hover:bg-brand-50 transition-colors"
          >
            <span>مشاهده همه کمپین‌ها</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="19" y1="12" x2="5" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
          </Link>
        </div>
      </div>

      {/* ── Album lightbox ───────────────────────────────────────────── */}
      <CampaignAlbum
        open={album.open}
        onClose={closeAlbum}
        title={album.title}
        sponsor={album.sponsor}
        images={album.images}
        loading={album.loading}
      />
    </section>
  );
}
