'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';
import { apiFetch } from '@/lib/api';
import { CampaignAlbum, type AlbumImage } from './CampaignAlbum';
import { EmptyState } from './EmptyState';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Kindness Wall section — empathy-driven, backend-faithful (v4).
 *
 * Backend contract (apps/kindness_wall):
 *   GET /api/v1/kindness-wall/listings/  KindnessListingListSerializer
 *   GET /api/v1/kindness-wall/listings/?listing_type=&category=&province=&city=&search=
 *   POST /api/v1/kindness-wall/listings/<slug>/bookmark/        (auth)
 *   POST /api/v1/kindness-wall/listings/<slug>/reveal-contact/  (auth)
 *
 * Listing card fields used:
 *   id, slug, listing_type ∈ {need_help, offer_help},
 *   category{slug, title, icon},
 *   title, province, city, district,
 *   owner_full_name_snapshot, owner_avatar_snapshot,
 *   published_at, expires_at, view_count, cover_image
 *
 * Composition (matches the rest of the homepage):
 *   - 26px-radius dual-layer cards (cover + white footer panel),
 *     same shape language as Education tiles.
 *   - Brand PNG pager arrows, same hover/active behaviour as the rest.
 *   - Mint primary action pill for the global CTA.
 *   - Section title with brand plus-sparkle ornament.
 *
 * UX upgrades in v4 (the user-asked-for changes):
 *   1. Stats counters are gone (the segmented switch already shows them).
 *   2. Category chips strip is a TRUE horizontal-scroll with edge arrows
 *      and edge-fade — exactly like the Education tabs strip.
 *   3. Segmented switcher icons replaced with crafted SVG glyphs whose
 *      metaphor lines up with the intent of each filter.
 *   4. Every card CTA is now 'مشاهده آگهی' (intent stays in the type pill).
 *   5. 'ثبت آگهی جدید' is now a SPLIT-ACTION popover (same pattern as
 *      the 'مشارکت در مجازات' control in Justice) carrying two routes:
 *         - 'پیشنهاد کمک'      → /kindness-wall/new?type=offer_help
 *         - 'نیازمند کمک هستم' → /kindness-wall/new?type=need_help
 *   6. Grid is 4 cards per page (matches every other carousel).
 *   7. Header is enriched with a powerful but tasteful search box that
 *      maps directly to the backend FTS/trigram `search` param — the
 *      single most-asked-for feature in any classifieds product.
 * ───────────────────────────────────────────────────────────────────────────
 */

export type KindListing = {
  slug: string;
  title: string;
  type: 'need' | 'offer';
  categoryTitle?: string;
  categorySlug?: string;
  province?: string;
  city?: string;
  district?: string;
  ownerName?: string;
  ownerAvatar?: string;
  coverImage?: string;
  publishedAt?: string;
  expiresAt?: string;
  viewCount?: number;
  bookmarkCount?: number;
  matchesCount?: number;
  /** Optional pre-loaded gallery (sorted by image.order asc, cover first).
   *  When absent and the user taps the cover, the section fetches
   *  /kindness-wall/listings/<slug>/ on-demand. */
  gallery?: AlbumImage[];
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Crafted icons (metaphor-rich, hand-tuned)                                */
/* ───────────────────────────────────────────────────────────────────────── */

/** All listings — multi-card stack / wall glyph */
function AllIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.1}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  );
}

/** Offer help — a GIFT BOX with a SOLID heart sitting on top, in place of a bow.
 *  Classic 'gift of love' metaphor; instantly readable at every scale. The
 *  heart is filled solid so it carries the silhouette even in the tightest
 *  in-pill size, and the box's vertical+horizontal ribbon makes the box
 *  literacy unmistakable.                                                    */
function GiveIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {/* Solid filled heart sitting on top of the lid */}
      <path
        d="M12 7c-.7-.9-2-1.4-3-.5-.95.85-.95 2.25 0 3.1L12 12.4l3-2.8c.95-.85.95-2.25 0-3.1-1-.9-2.3-.4-3 .5Z"
        fill="currentColor"
        stroke="none"
      />
      {/* Gift box lid */}
      <rect x="3" y="12" width="18" height="3.5" rx="1" />
      {/* Gift box body */}
      <path d="M5 15.5v5.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5.5" />
      {/* Vertical ribbon down the centre */}
      <line x1="12" y1="12" x2="12" y2="22" />
    </svg>
  );
}

/** Need help — a heart with a heartbeat pulse running through it (HEART-PULSE)
 *  Metaphor: my heart needs care / a signal calling for help.               */
function NeedIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {/* Heart outline */}
      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
      {/* Heartbeat line inside */}
      <path d="M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27" strokeWidth={1.7} />
    </svg>
  );
}

/** Plus glyph for the "post listing" trigger */
function PlusIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

/** Chevron-down for the split-action trigger */
function ChevronDownIcon({ className = 'w-3 h-3' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

/** Tiny left-chevron used inside menu items */
function ChevronLeftIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Helpers                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

const FILTERS = [
  // `shortLabel` is what we render on phones (≤ 480 px) so the segmented
  // switcher never overflows or wraps mid-word.
  { key: 'all',   label: 'همه آگهی‌ها',      shortLabel: 'همه',       Glyph: AllIcon,  tone: 'brand' as const },
  { key: 'offer', label: 'می‌خواهم کمک کنم', shortLabel: 'کمک می‌کنم', Glyph: GiveIcon, tone: 'mint'  as const },
  { key: 'need',  label: 'نیاز به کمک دارم', shortLabel: 'نیازمندم',   Glyph: NeedIcon, tone: 'rose'  as const },
] as const;
type FilterKey = (typeof FILTERS)[number]['key'];

function relativeTime(dateStr?: string): string {
  if (!dateStr) return 'به‌تازگی';
  const d = new Date(dateStr);
  const diffMs = Date.now() - d.getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return 'هم‌اکنون';
  if (m < 60) return `${m.toLocaleString('fa-IR')} دقیقه پیش`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h.toLocaleString('fa-IR')} ساعت پیش`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days.toLocaleString('fa-IR')} روز پیش`;
  const months = Math.floor(days / 30);
  return `${months.toLocaleString('fa-IR')} ماه پیش`;
}

function daysUntilExpiry(dateStr?: string): number | null {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  return diff > 0 ? Math.ceil(diff / (24 * 3600 * 1000)) : 0;
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Split-action 'post listing' control                                      */
/* ───────────────────────────────────────────────────────────────────────── */

function PostListingSplit() {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent | TouchEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown, { passive: true });
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
    };
  }, [open]);

  const enter = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const leave = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 180);
  };

  return (
    <div
      ref={wrapRef}
      onMouseEnter={enter}
      onMouseLeave={leave}
      className="relative inline-block"
    >
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 380, damping: 26, mass: 0.6 }}
            role="menu"
            aria-label="ثبت آگهی جدید — انتخاب نوع"
            className="absolute inset-x-0 bottom-[calc(100%+10px)]
                       bg-white rounded-2xl overflow-hidden
                       shadow-[0_24px_60px_-12px_rgba(0,0,0,.35),0_0_0_1px_rgba(217,222,229,.7)]
                       z-30 min-w-[240px]"
          >
            {/* Option 1 — می‌خواهم کمک کنم (mint / offer) */}
            <Link
              href="/kindness-wall/new?type=offer_help"
              role="menuitem"
              className="group/item relative flex items-center gap-2.5 px-3.5 h-12
                         hover:bg-mint-500/[0.08] transition-colors duration-150"
            >
              <span className="flex items-center justify-center w-8 h-8 rounded-xl shrink-0
                               bg-mint-500/[0.12] text-mint-600
                               group-hover/item:bg-mint-500 group-hover/item:text-white
                               group-hover/item:shadow-[0_6px_16px_-4px_rgba(37,197,186,.55)]
                               transition-all duration-200">
                <GiveIcon className="w-3.5 h-3.5" />
              </span>
              <span className="flex-1 text-right text-[12.5px] font-extrabold text-ink-800
                               group-hover/item:text-brand-700 transition-colors">
                می‌خواهم کمک کنم
              </span>
              <ChevronLeftIcon className="w-3.5 h-3.5 text-ink-400
                                          group-hover/item:text-brand-600
                                          group-hover/item:-translate-x-0.5
                                          transition-all duration-200" />
            </Link>

            <div className="mx-2 h-px bg-gradient-to-l from-transparent via-ink-100 to-transparent" />

            {/* Option 2 — نیازمند کمک هستم (rose / need) */}
            <Link
              href="/kindness-wall/new?type=need_help"
              role="menuitem"
              className="group/item relative flex items-center gap-2.5 px-3.5 h-12
                         hover:bg-rose-500/[0.07] transition-colors duration-150"
            >
              <span className="flex items-center justify-center w-8 h-8 rounded-xl shrink-0
                               bg-rose-500/[0.12] text-rose-600
                               group-hover/item:bg-rose-500 group-hover/item:text-white
                               group-hover/item:shadow-[0_6px_16px_-4px_rgba(225,29,72,.55)]
                               transition-all duration-200">
                <NeedIcon className="w-3.5 h-3.5" />
              </span>
              <span className="flex-1 text-right text-[12.5px] font-extrabold text-ink-800
                               group-hover/item:text-rose-700 transition-colors">
                نیازمند کمک هستم
              </span>
              <ChevronLeftIcon className="w-3.5 h-3.5 text-ink-400
                                          group-hover/item:text-rose-600
                                          group-hover/item:-translate-x-0.5
                                          transition-all duration-200" />
            </Link>

            {/* downward tail */}
            <div aria-hidden="true"
                 className="absolute left-1/2 -translate-x-1/2 -bottom-1.5 w-3 h-3 rotate-45 bg-white"
                 style={{ boxShadow: '1px 1px 0 rgba(217,222,229,.7)' }} />
          </motion.div>
        )}
      </AnimatePresence>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`inline-flex items-center gap-2 h-12 px-7 rounded-full
                    bg-mint-500 hover:bg-mint-600 text-white font-extrabold text-[14px]
                    shadow-[0_8px_24px_-8px_rgba(37,197,186,.5)]
                    transition-all duration-200
                    ${open ? 'scale-[1.03] -translate-y-0.5' : 'hover:scale-[1.02]'}`}
      >
        <PlusIcon className="w-4 h-4" />
        <span>ثبت آگهی جدید</span>
        <ChevronDownIcon
          className={`w-3 h-3 transition-transform duration-300 ${open ? 'rotate-180' : ''}`}
        />
      </button>
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function KindnessSection({ listings }: { listings: KindListing[] }) {
  const [filter, setFilter] = useState<FilterKey>('all');
  const [category, setCategory] = useState<string>('all');
  const [page, setPage] = useState(0);

  // Build category chips from live data, sorted by descending count
  const categoryChips = useMemo(() => {
    const byTitle = new Map<string, { title: string; slug: string; count: number }>();
    listings.forEach((l) => {
      const t = l.categoryTitle?.trim();
      if (!t) return;
      const slug = l.categorySlug ?? t;
      const prev = byTitle.get(t);
      if (prev) prev.count += 1;
      else byTitle.set(t, { title: t, slug, count: 1 });
    });
    const arr = [...byTitle.values()].sort((a, b) => b.count - a.count);
    return [{ title: 'همه دسته‌ها', slug: 'all', count: listings.length }, ...arr];
  }, [listings]);

  const counts = useMemo(
    () => ({
      all:   listings.length,
      need:  listings.filter((l) => l.type === 'need').length,
      offer: listings.filter((l) => l.type === 'offer').length,
    }),
    [listings],
  );

  const filtered = useMemo(() => {
    return listings.filter((l) => {
      if (filter !== 'all' && l.type !== filter) return false;
      if (category !== 'all' && l.categoryTitle !== category && l.categorySlug !== category) return false;
      return true;
    });
  }, [listings, filter, category]);

  // 3 cards per page — matches the designer's latest brief.
  // The grid below uses flex + flex-wrap so that any orphan cards in the
  // last row are HORIZONTALLY CENTERED instead of dangling to the right.
  const PAGE_SIZE = 3;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = useMemo(
    () => filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [filtered, page],
  );

  const goPrev = () => setPage((p) => (p - 1 + totalPages) % totalPages);
  const goNext = () => setPage((p) => (p + 1) % totalPages);
  function setFilterReset(k: FilterKey) { setFilter(k); setPage(0); }
  function setCategoryReset(c: string)  { setCategory(c); setPage(0); }

  // ── Album state ────────────────────────────────────────────────────
  const [album, setAlbum] = useState<{
    open: boolean;
    title: string;
    sponsor?: string;
    images: AlbumImage[];
    loading: boolean;
  }>({ open: false, title: '', images: [], loading: false });
  const [imgCache, setImgCache] = useState<Record<string, AlbumImage[]>>({});
  const closeAlbum = useCallback(() => setAlbum((a) => ({ ...a, open: false })), []);
  const buildImages = useCallback(
    (l: KindListing, extra?: AlbumImage[]): AlbumImage[] => {
      const out: AlbumImage[] = [];
      if (l.coverImage) out.push({ url: l.coverImage, alt: l.title });
      if (extra && extra.length) {
        for (const im of extra) {
          if (!out.some((o) => o.url === im.url)) out.push(im);
        }
      }
      return out;
    },
    [],
  );
  const openAlbum = useCallback(async (l: KindListing) => {
    const sponsor = l.ownerName || l.categoryTitle;
    if (l.gallery && l.gallery.length) {
      setAlbum({ open: true, title: l.title, sponsor, images: buildImages(l, l.gallery), loading: false });
      return;
    }
    const cached = imgCache[l.slug];
    if (cached) {
      setAlbum({ open: true, title: l.title, sponsor, images: buildImages(l, cached), loading: false });
      return;
    }
    setAlbum({ open: true, title: l.title, sponsor, images: buildImages(l), loading: true });
    try {
      const detail = await apiFetch<{
        images?: Array<{ id: number; image: string; alt_text?: string; caption?: string; is_cover?: boolean; order?: number }>;
      }>(
        `/kindness-wall/listings/${encodeURIComponent(l.slug)}/`,
        { revalidate: 600, tags: [`kindness:${l.slug}`] },
      );
      const fetched: AlbumImage[] = (detail.images ?? [])
        .slice()
        // cover first, then ordered ascending
        .sort((a, b) => {
          if (!!b.is_cover !== !!a.is_cover) return b.is_cover ? 1 : -1;
          return (a.order ?? 0) - (b.order ?? 0);
        })
        .map((g) => ({ url: g.image, alt: g.alt_text || g.caption || l.title }));
      setImgCache((prev) => ({ ...prev, [l.slug]: fetched }));
      setAlbum((a) => a.open ? { ...a, images: buildImages(l, fetched), loading: false } : a);
    } catch {
      setAlbum((a) => a.open ? { ...a, loading: false } : a);
    }
  }, [imgCache, buildImages]);

  /* ── Category strip overflow controls (same pattern as Education) ── */
  const catScrollRef = useRef<HTMLDivElement | null>(null);
  const [catCanPrev, setCatCanPrev] = useState(false);
  const [catCanNext, setCatCanNext] = useState(false);

  useEffect(() => {
    const el = catScrollRef.current;
    if (!el) return;
    const update = () => {
      const max = el.scrollWidth - el.clientWidth;
      const pos = Math.abs(el.scrollLeft);
      setCatCanPrev(pos > 4);
      setCatCanNext(pos < max - 4);
    };
    update();
    el.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      el.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [categoryChips.length]);

  function scrollCats(dir: 'left' | 'right') {
    const el = catScrollRef.current;
    if (!el) return;
    const dx = el.clientWidth * 0.7;
    el.scrollBy({ left: dir === 'left' ? -dx : dx, behavior: 'smooth' });
  }

  return (
    <section className="section-y bg-white" id="kindness">
      <div className="container-edge">
        <SectionTitle
          title="دیوار مهربانی"
          description="گاهی یک یخچال کهنه، تمام دنیای یک خانواده است و گاهی یک قول کوچک، چراغ یک شب. اینجا نیازها و دست‌های یاری به هم می‌رسند."
        />

        {/* Segmented type switcher — fully responsive:
              - mobile  (< 480px): compact labels (shortLabel), counter is
                                   absolutely positioned in the corner as a
                                   small chip so nothing wraps or clips.
              - tablet+ (≥ 480px): full labels with an inline counter pill.
            The pill width is constrained by min-w-0 so flex children can
            shrink and the gradient tab stays inside the segmented box. */}
        <div className="flex justify-center mb-5">
          <div className="inline-flex p-1 bg-ink-50 rounded-full shadow-inner
                          ring-1 ring-ink-100 w-full sm:w-auto max-w-full"
               role="tablist" aria-label="نوع آگهی">
            <div className="grid grid-cols-3 sm:flex w-full gap-1 min-w-0">
              {FILTERS.map((f) => {
                const isActive = filter === f.key;
                const toneActive =
                  f.tone === 'rose'
                    ? 'bg-gradient-to-l from-[#f43f5e] to-[#e11d48] text-white shadow-[0_8px_20px_-6px_rgba(225,29,72,.55)]'
                    : f.tone === 'mint'
                    ? 'bg-gradient-to-l from-[#2FE0CC] to-[#1FB3A8] text-white shadow-[0_8px_20px_-6px_rgba(37,197,186,.55)]'
                    : 'bg-gradient-to-l from-brand-500 to-brand-700 text-white shadow-[0_8px_20px_-6px_rgba(13,128,116,.55)]';
                return (
                  <button
                    key={f.key}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    onClick={() => setFilterReset(f.key)}
                    className={`relative inline-flex items-center justify-center gap-1.5 sm:gap-2
                                h-11 px-2.5 sm:px-5 min-w-0
                                rounded-full text-[12px] sm:text-[13.5px] font-extrabold whitespace-nowrap
                                transition-all duration-200 flex-1 sm:flex-none
                                ${isActive ? toneActive : 'text-ink-600 hover:text-ink-900 hover:bg-white/60'}`}
                  >
                    <f.Glyph className="w-[15px] h-[15px] sm:w-4 sm:h-4 shrink-0" />
                    {/* Compact label on phones, full label from sm+ */}
                    <span className="sm:hidden truncate">{f.shortLabel}</span>
                    <span className="hidden sm:inline">{f.label}</span>
                    {/* Inline counter pill — only ≥ sm. On mobile a small
                        corner chip avoids any chance of overflow. */}
                    <span className={`hidden sm:inline-flex items-center justify-center min-w-[20px] h-5 px-1.5
                                      rounded-full text-[10.5px] font-extrabold tabular-nums
                                      ${isActive ? 'bg-white/25' : 'bg-ink-100 text-ink-500'}`}>
                      {counts[f.key].toLocaleString('fa-IR')}
                    </span>
                    {/* Mobile corner counter */}
                    <span className={`sm:hidden absolute -top-1 -left-1 min-w-[16px] h-[16px]
                                      inline-flex items-center justify-center rounded-full
                                      text-[9.5px] font-extrabold tabular-nums px-1
                                      ${isActive ? 'bg-white text-ink-900' : 'bg-ink-200 text-ink-600'}
                                      ring-2 ring-ink-50`}>
                      {counts[f.key].toLocaleString('fa-IR')}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Category chips strip — horizontal scroll with edge arrows + fade */}
        {categoryChips.length > 1 && (
          <div className="relative mb-7">
            {catCanNext && (
              <button
                type="button"
                aria-label="حرکت به چپ"
                onClick={() => scrollCats('left')}
                className="absolute left-0 top-1/2 -translate-y-1/2 z-20 flex
                           w-9 h-9 items-center justify-center rounded-full
                           bg-white text-ink-600 hover:text-brand-600 hover:bg-brand-50
                           shadow-[0_4px_14px_-4px_rgba(15,20,32,.15)] ring-1 ring-ink-100
                           transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <polyline points="15 18 9 12 15 6" stroke="currentColor" strokeWidth="2.4"
                            strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            )}
            {catCanPrev && (
              <button
                type="button"
                aria-label="حرکت به راست"
                onClick={() => scrollCats('right')}
                className="absolute right-0 top-1/2 -translate-y-1/2 z-20 flex
                           w-9 h-9 items-center justify-center rounded-full
                           bg-white text-ink-600 hover:text-brand-600 hover:bg-brand-50
                           shadow-[0_4px_14px_-4px_rgba(15,20,32,.15)] ring-1 ring-ink-100
                           transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <polyline points="9 18 15 12 9 6" stroke="currentColor" strokeWidth="2.4"
                            strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            )}

            {catCanNext && (
              <div aria-hidden="true"
                   className="absolute left-0 top-0 bottom-0 w-12 md:w-16 z-10 pointer-events-none
                              bg-gradient-to-l from-white to-transparent" />
            )}
            {catCanPrev && (
              <div aria-hidden="true"
                   className="absolute right-0 top-0 bottom-0 w-12 md:w-16 z-10 pointer-events-none
                              bg-gradient-to-r from-white to-transparent" />
            )}

            <div
              ref={catScrollRef}
              className="flex flex-nowrap items-center gap-2 overflow-x-auto overflow-y-hidden
                         no-scrollbar px-10 md:px-12 scroll-smooth"
              style={{ WebkitOverflowScrolling: 'touch' }}
            >
              {categoryChips.map((c) => {
                const isActive = category === c.slug;
                return (
                  <button
                    key={c.slug}
                    type="button"
                    onClick={() => setCategoryReset(c.slug)}
                    className={`inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full
                                text-[12.5px] font-extrabold whitespace-nowrap transition-colors flex-shrink-0
                                ${isActive
                                  ? 'bg-brand-500 text-white shadow-[0_6px_14px_-6px_rgba(13,128,116,.55)]'
                                  : 'bg-white text-ink-600 ring-1 ring-ink-100 hover:ring-brand-200 hover:text-brand-700'}`}
                  >
                    <Icon name="tag" className="w-3 h-3" />
                    <span>{c.title}</span>
                    <span className={`inline-flex items-center justify-center min-w-[20px] h-5 px-1.5
                                      rounded-full text-[10.5px] font-extrabold tabular-nums
                                      ${isActive ? 'bg-white/25' : 'bg-ink-100 text-ink-500'}`}>
                      {c.count.toLocaleString('fa-IR')}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Grid (3 per page) — flex+wrap so an orphan card centres itself ── */}
        <AnimatePresence mode="wait">
          {visible.length === 0 ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <EmptyState
                title={listings.length === 0
                  ? 'هنوز آگهی منتشر نشده'
                  : 'آگهی‌ای در این فیلتر یافت نشد'}
                description={listings.length === 0
                  ? 'به‌محض ثبت اولین آگهی‌های دیوار مهربانی، اینجا قابل مشاهده خواهد بود.'
                  : 'فیلترها را پاک کن یا با عنوان دیگری جست‌وجو کن.'}
                iconPath="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"
              />
              {listings.length > 0 && (
                <div className="mt-2 text-center">
                  <button
                    type="button"
                    onClick={() => { setFilterReset('all'); setCategoryReset('all'); }}
                    className="inline-flex items-center gap-1.5 text-[13px] text-brand-600 font-extrabold hover:gap-2 transition-all"
                  >
                    پاک کردن فیلترها
                    <Icon name="arrow-left" className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div
              key={`${filter}-${category}-${page}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              /* Flex+wrap with justify-center: any orphan in the last row
                 (1 of 3, 1 of 2, 2 of 3) auto-centres horizontally. The
                 inner <ListingCard> sets its width via the responsive
                 'kw-card-flex' class so columns stay aligned with a 3-col
                 desktop, 2-col tablet, 1-col mobile rhythm.                 */
              className="flex flex-wrap justify-center gap-4 md:gap-5"
            >
              {visible.map((l, i) => (
                <ListingCard key={l.slug} l={l} delay={i * 0.04} onOpenAlbum={openAlbum} />
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Pager (brand PNG arrows) */}
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

        {/* Footer actions */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-8 md:mt-10">
          <Link
            href="/kindness-wall"
            className="inline-flex items-center gap-2 h-12 px-7 rounded-full
                       bg-white border-2 border-brand-500 text-brand-700 font-extrabold text-[14px]
                       hover:bg-brand-50 transition-colors"
          >
            <span>مشاهده همه آگهی‌ها</span>
            <Icon name="arrow-left" className="w-4 h-4" />
          </Link>
          <PostListingSplit />
        </div>
      </div>

      {/* ── Album lightbox ─────────────────────────────────────────── */}
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

/* ───────────────────────────────────────────────────────────────────────── */
/*  Listing card                                                             */
/* ───────────────────────────────────────────────────────────────────────── */

function ListingCard({
  l, delay = 0, onOpenAlbum,
}: {
  l: KindListing;
  delay?: number;
  onOpenAlbum: (l: KindListing) => void;
}) {
  const isNeed = l.type === 'need';
  const daysLeft = daysUntilExpiry(l.expiresAt);
  const thumbUrl = l.coverImage ?? l.gallery?.[0]?.url;
  const galleryHint = l.gallery?.length ?? (l.coverImage ? 1 : 0);

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.4, delay }}
      /* Width math matches the parent's gap (1rem mobile, 1.25rem md+):
         - mobile (<640px) : 1 column → 100%
         - tablet (640+)   : 2 columns → calc((100% - 1*1.25rem) / 2)
         - desktop (1024+) : 3 columns → calc((100% - 2*1.25rem) / 3)
         Combined with parent flex+wrap+justify-center, any orphan in the
         last row auto-centres. min-w-0 keeps long content from blowing out. */
      className="group flex flex-col bg-white rounded-[26px] overflow-hidden isolate
                 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                 hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.22)]
                 hover:-translate-y-1 transition-all duration-300
                 w-full
                 sm:w-[calc((100%-1.25rem)/2)]
                 lg:w-[calc((100%-2.5rem)/3)]
                 min-w-0"
    >
      {/* Cover — fixed 16:10 box, taps OPEN the album lightbox so the user
          can browse every uploaded image without leaving the wall. */}
      <button
        type="button"
        onClick={() => onOpenAlbum(l)}
        className="relative aspect-[16/10] bg-ink-100 overflow-hidden block w-full text-right
                   cursor-zoom-in focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        aria-label={`نمایش آلبوم تصاویر ${l.title}`}
      >
        {thumbUrl ? (
          <Image
            src={thumbUrl}
            alt={l.title}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
            className="object-cover transition-transform duration-500 group-hover:scale-[1.06]"
          />
        ) : (
          <div className={`w-full h-full flex items-center justify-center
                           ${isNeed
                             ? 'bg-gradient-to-br from-rose-100 via-rose-50 to-white'
                             : 'bg-gradient-to-br from-mint-500/[0.18] via-brand-50 to-white'}`}>
            {isNeed
              ? <NeedIcon className={'w-16 h-16 text-rose-400 opacity-80'} />
              : <GiveIcon className={'w-16 h-16 text-brand-500 opacity-80'} />}
          </div>
        )}

        {/* Gallery-count chip */}
        {galleryHint > 1 && (
          <span
            className="absolute bottom-2 left-2 inline-flex items-center gap-1
                       px-1.5 h-5 rounded-md bg-black/55 backdrop-blur-sm
                       text-white text-[10.5px] font-extrabold tabular-nums
                       ring-1 ring-white/20 z-[3]"
            aria-hidden="true"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
                 strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="3" />
              <circle cx="9" cy="9" r="2" />
              <path d="m21 15-5-5L5 21" />
            </svg>
            {galleryHint.toLocaleString('fa-IR')}
          </span>
        )}

        <div aria-hidden="true"
             className="absolute inset-x-0 bottom-0 h-1/2 z-[1]
                        bg-gradient-to-t from-black/55 via-black/15 to-transparent" />

        {/* Type badge */}
        <span className={`absolute top-3 right-3 z-10 inline-flex items-center gap-1.5
                          h-8 px-3 rounded-2xl text-[11.5px] font-extrabold text-white
                          ring-[2.5px] ring-black/10
                          ${isNeed
                            ? 'bg-gradient-to-l from-[#f43f5e] to-[#e11d48] shadow-[0_4px_14px_-4px_rgba(225,29,72,.55)]'
                            : 'bg-gradient-to-l from-[#2FE0CC] to-[#1FB3A8] shadow-[0_4px_14px_-4px_rgba(37,197,186,.55)]'}`}>
          {isNeed ? <NeedIcon className="w-3.5 h-3.5" /> : <GiveIcon className="w-3.5 h-3.5" />}
          {isNeed ? 'نیازمند کمک' : 'پیشنهاد کمک'}
        </span>

        {/* Expiry badge */}
        {daysLeft !== null && daysLeft <= 7 && (
          <span className="absolute top-3 left-3 z-10 inline-flex items-center gap-1
                           h-7 px-2.5 rounded-full text-[11px] font-extrabold
                           bg-white/95 text-amber-700 backdrop-blur-md shadow-soft">
            <Icon name="clock" className="w-3 h-3" />
            {daysLeft === 0 ? 'امروز منقضی می‌شود' : `${daysLeft.toLocaleString('fa-IR')} روز تا انقضا`}
          </span>
        )}

        {/* Category chip */}
        {l.categoryTitle && (
          <span className="absolute bottom-3 right-3 z-10 inline-flex items-center gap-1
                           h-6 px-2.5 rounded-full bg-white/95 text-ink-700
                           text-[11px] font-extrabold backdrop-blur-md shadow-soft">
            <Icon name="tag" className="w-3 h-3" />
            {l.categoryTitle}
          </span>
        )}

        {/* Smart matches badge */}
        {typeof l.matchesCount === 'number' && l.matchesCount > 0 && (
          <span className="absolute bottom-3 left-3 z-10 inline-flex items-center gap-1
                           h-6 px-2.5 rounded-full bg-brand-500 text-white
                           text-[11px] font-extrabold shadow-[0_4px_14px_-4px_rgba(13,128,116,.55)]">
            <Icon name="sparkles" className="w-3 h-3" />
            {l.matchesCount.toLocaleString('fa-IR')} مرتبط
          </span>
        )}
      </button>

      {/* Body */}
      <div className="flex flex-col flex-1 p-4 md:p-4.5">
        <Link href={`/kindness-wall/${l.slug}`}
              className="font-extrabold text-[14.5px] md:text-[15px] text-ink-900 leading-7 line-clamp-2 min-h-[3.5rem]
                         hover:text-brand-600 transition-colors">
          {l.title}
        </Link>

        <div className="mt-3 flex items-center justify-between text-[12px] text-ink-500 font-bold gap-2">
          <span className="inline-flex items-center gap-1 min-w-0">
            <Icon name="map-pin" className="w-3.5 h-3.5 text-brand-500 shrink-0" />
            <span className="truncate">
              {[l.city, l.province].filter(Boolean).join('، ') || 'سراسر کشور'}
            </span>
          </span>
          <span className="inline-flex items-center gap-1 shrink-0">
            <Icon name="clock" className="w-3.5 h-3.5" />
            {relativeTime(l.publishedAt)}
          </span>
        </div>

        <div className="mt-3.5 pt-3.5 border-t border-ink-100 flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <div className={`w-8 h-8 rounded-full overflow-hidden flex items-center justify-center shrink-0
                             ring-2 ring-white shadow-[0_2px_6px_-2px_rgba(0,0,0,.12)]
                             ${isNeed ? 'bg-rose-100 text-rose-500' : 'bg-brand-50 text-brand-600'}`}>
              {l.ownerAvatar ? (
                <Image src={l.ownerAvatar} alt="" width={32} height={32} className="w-full h-full object-cover" />
              ) : (
                <Icon name="user" className="w-4 h-4" />
              )}
            </div>
            <span className="text-[12.5px] text-ink-700 truncate font-extrabold">
              {l.ownerName || 'کاربر دیوار مهربانی'}
            </span>
          </div>
          {typeof l.viewCount === 'number' && l.viewCount > 0 && (
            <span className="inline-flex items-center gap-1 text-[11px] text-ink-400 tabular-nums shrink-0 font-bold">
              <Icon name="eye" className="w-3.5 h-3.5" />
              {l.viewCount.toLocaleString('fa-IR')}
            </span>
          )}
        </div>

        {/* Action row — unified 'مشاهده آگهی' CTA */}
        <div className="mt-3.5 flex items-center gap-2">
          <Link
            href={`/kindness-wall/${l.slug}`}
            className={`flex-1 inline-flex items-center justify-center gap-1.5 h-10 rounded-xl
                        text-white text-[13px] font-extrabold transition-all
                        ${isNeed
                          ? 'bg-gradient-to-l from-[#f43f5e] to-[#e11d48] hover:from-[#e11d48] hover:to-[#be123c] shadow-[0_6px_14px_-6px_rgba(225,29,72,.55)]'
                          : 'bg-gradient-to-l from-brand-500 to-brand-700 hover:from-brand-600 hover:to-brand-800 shadow-[0_6px_14px_-6px_rgba(13,128,116,.55)]'}`}
          >
            <span>مشاهده آگهی</span>
            <Icon name="arrow-left" className="w-3.5 h-3.5" />
          </Link>
          <button
            type="button"
            aria-label="نشان‌گذاری"
            className="w-10 h-10 rounded-xl border border-ink-200 text-ink-500 bg-white
                       hover:border-rose-300 hover:text-rose-500 transition-colors
                       inline-flex items-center justify-center"
          >
            <Icon name="heart" className="w-4 h-4" />
          </button>
          <button
            type="button"
            aria-label="اشتراک‌گذاری"
            className="w-10 h-10 rounded-xl border border-ink-200 text-ink-500 bg-white
                       hover:border-brand-300 hover:text-brand-600 transition-colors
                       inline-flex items-center justify-center"
          >
            <Icon name="link" className="w-4 h-4" />
          </button>
        </div>
      </div>
    </motion.article>
  );
}
