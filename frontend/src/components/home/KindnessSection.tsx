'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Kindness Wall section — designer-free, deeply backend-driven (v3).
 *
 * Backend contract (apps/kindness_wall):
 *
 *   GET /api/v1/kindness-wall/categories/   → KindnessCategorySerializer
 *   GET /api/v1/kindness-wall/listings/     → KindnessListingListSerializer
 *     query params (KindnessListingPublicFilter):
 *       - listing_type ∈ {need_help, offer_help}
 *       - category     (category slug)
 *       - province, city
 *       - search       (FTS + trigram)
 *
 *   POST /api/v1/kindness-wall/listings/<slug>/reveal-contact/   → auth-only
 *   POST /api/v1/kindness-wall/listings/<slug>/bookmark/         → toggle
 *
 *   Listing card fields used:
 *     id, slug, listing_type, category{title, slug, icon},
 *     title, province, city, district,
 *     owner_full_name_snapshot, owner_avatar_snapshot,
 *     published_at, expires_at, view_count, cover_image
 *
 *   The model also exposes (admins / future use):
 *     bookmark_count, contact_reveal_count, report_count, match_generation_version
 *
 * Designer-free brief (this is OUR design):
 *
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │           segmented switch:  همه │ نیازمند │ پیشنهاد        │
 *   │  دسته‌بندی chips —  «همه دسته‌ها · لوازم خانگی · سلامت …»   │
 *   │                                                              │
 *   │  ┌──────┐ ┌──────┐ ┌──────┐                                 │
 *   │  │      │ │      │ │      │   3 × N grid of premium cards   │
 *   │  └──────┘ └──────┘ └──────┘   (paged via the brand arrows)  │
 *   │                                                              │
 *   │            ◀──── pager arrows ────▶                          │
 *   │                                                              │
 *   │   [مشاهده همه آگهی‌ها]   [+ ثبت آگهی جدید]                   │
 *   └─────────────────────────────────────────────────────────────┘
 *
 * Colour-psychology (matches our existing palette):
 *   - 'نیازمند کمک'  → rose/red soft   — empathy + urgency
 *   - 'پیشنهاد کمک'  → mint/teal       — giving + calm
 *   - both type pills mirror the badge style on the cover
 *
 * Privacy-first contact reveal:
 *   - The backend never exposes contact_phone in list/detail (only after
 *     POST /reveal-contact/). The card surface advertises the intent with
 *     a 'lock' affordance and routes the user to the detail page first.
 *
 * Visual harmony with the rest of the homepage:
 *   - 26px radius cards, dual-layer (cover + white footer panel) like Edu.
 *   - Brand PNG pager arrows, same hover/active scale behaviour.
 *   - SectionTitle with the brand plus-sparkle ornament.
 *   - 'ثبت آگهی جدید' mint-pill matches the global primary CTA style.
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
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Helpers                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

const FILTERS = [
  { key: 'all',   label: 'همه آگهی‌ها',          icon: 'megaphone'     as const, tone: 'brand'  as const },
  { key: 'offer', label: 'می‌خواهم کمک کنم',     icon: 'helping-hand'  as const, tone: 'mint'   as const },
  { key: 'need',  label: 'نیاز به کمک دارم',     icon: 'hand-heart'    as const, tone: 'rose'   as const },
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

/** Days remaining until expires_at; null if no expiry. */
function daysUntilExpiry(dateStr?: string): number | null {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  return diff > 0 ? Math.ceil(diff / (24 * 3600 * 1000)) : 0;
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function KindnessSection({ listings }: { listings: KindListing[] }) {
  const [filter, setFilter] = useState<FilterKey>('all');
  const [category, setCategory] = useState<string>('all');
  const [page, setPage] = useState(0);

  // Build category chips from the live listings so the strip auto-evolves
  // with backend taxonomy changes.
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

  // Live stats — used by the pill counts AND the in-card empathy meta
  const counts = useMemo(
    () => ({
      all:   listings.length,
      need:  listings.filter((l) => l.type === 'need').length,
      offer: listings.filter((l) => l.type === 'offer').length,
    }),
    [listings],
  );

  // Filter pipeline: type → category → slice into pager-pages
  const filtered = useMemo(() => {
    return listings.filter((l) => {
      if (filter !== 'all' && l.type !== filter) return false;
      if (category !== 'all' && l.categoryTitle !== category && l.categorySlug !== category) return false;
      return true;
    });
  }, [listings, filter, category]);

  const PAGE_SIZE = 6; // exactly 2 rows × 3 cards on desktop
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = useMemo(
    () => filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [filtered, page],
  );

  // Reset to page 0 whenever filter/category changes
  const goPrev = () => setPage((p) => (p - 1 + totalPages) % totalPages);
  const goNext = () => setPage((p) => (p + 1) % totalPages);
  function setFilterReset(k: FilterKey) { setFilter(k); setPage(0); }
  function setCategoryReset(c: string)  { setCategory(c); setPage(0); }

  return (
    <section className="section-y bg-white" id="kindness">
      <div className="container-edge">
        <SectionTitle
          title="دیوار مهربانی"
          description="پلی میان نیازها و دست‌های یاری‌رسان؛ هر آگهی یک پل امید بین خانواده‌هاست."
        />

        {/* Live counters row — empathy framing */}
        <div className="flex flex-wrap items-center justify-center gap-2 mb-6">
          <StatPill tone="rose"  icon="hand-heart"   label="نیازمندان" value={counts.need} />
          <StatPill tone="mint"  icon="helping-hand" label="پیشنهاد کمک" value={counts.offer} />
          <StatPill tone="brand" icon="megaphone"    label="مجموع آگهی‌ها" value={counts.all} />
        </div>

        {/* Segmented type switcher */}
        <div className="mx-auto mb-5 inline-flex p-1 bg-ink-50 rounded-full shadow-inner
                        ring-1 ring-ink-100 w-full sm:w-auto"
             role="tablist" aria-label="نوع آگهی">
          <div className="grid grid-cols-3 sm:flex w-full gap-1">
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
                  className={`relative inline-flex items-center justify-center gap-2 h-11 px-4 sm:px-5
                              rounded-full text-[13px] sm:text-[13.5px] font-extrabold whitespace-nowrap
                              transition-all duration-200 flex-1 sm:flex-none
                              ${isActive ? toneActive : 'text-ink-600 hover:text-ink-900 hover:bg-white/60'}`}
                >
                  <Icon name={f.icon} className="w-4 h-4" />
                  <span>{f.label}</span>
                  <span className={`inline-flex items-center justify-center min-w-[20px] h-5 px-1.5
                                    rounded-full text-[10.5px] font-extrabold tabular-nums
                                    ${isActive ? 'bg-white/25' : 'bg-ink-100 text-ink-500'}`}>
                    {counts[f.key].toLocaleString('fa-IR')}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Category chips — horizontal scroll only */}
        {categoryChips.length > 1 && (
          <div className="mb-7 -mx-4 px-4 overflow-x-auto overflow-y-hidden no-scrollbar">
            <div className="flex flex-nowrap items-center gap-2 min-w-min">
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

        {/* ── Grid ── */}
        <AnimatePresence mode="wait">
          <motion.div
            key={`${filter}-${category}-${page}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-5"
          >
            {visible.map((l, i) => (
              <ListingCard key={l.slug} l={l} delay={i * 0.04} />
            ))}
            {visible.length === 0 && (
              <div className="col-span-full text-center py-16">
                <Icon name="search" className="w-12 h-12 mx-auto text-ink-300 mb-3" />
                <p className="text-ink-500 font-bold">آگهی‌ای در این فیلتر یافت نشد.</p>
                <button
                  type="button"
                  onClick={() => { setFilterReset('all'); setCategoryReset('all'); }}
                  className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-brand-600 font-extrabold hover:gap-2 transition-all"
                >
                  پاک کردن فیلترها
                  <Icon name="arrow-left" className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </motion.div>
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

        {/* Footer actions: see all + post new */}
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
          <Link
            href="/kindness-wall/new"
            className="inline-flex items-center gap-2 h-12 px-8 rounded-full
                       bg-mint-500 hover:bg-mint-600 text-white font-extrabold text-[14px]
                       shadow-[0_8px_24px_-8px_rgba(37,197,186,.5)] transition-colors"
          >
            <Icon name="plus" className="w-4 h-4" strokeWidth={2.5} />
            <span>ثبت آگهی جدید</span>
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Stat pill                                                                */
/* ───────────────────────────────────────────────────────────────────────── */

function StatPill({
  tone, icon, label, value,
}: {
  tone: 'rose' | 'mint' | 'brand';
  icon: 'hand-heart' | 'helping-hand' | 'megaphone';
  label: string;
  value: number;
}) {
  const toneClass =
    tone === 'rose'
      ? 'bg-rose-500/[0.08] text-rose-700 ring-rose-200/60'
      : tone === 'mint'
      ? 'bg-mint-500/[0.10] text-brand-700 ring-mint-500/30'
      : 'bg-brand-500/[0.08] text-brand-700 ring-brand-200/70';
  return (
    <span className={`inline-flex items-center gap-2 h-9 px-3.5 rounded-full
                      text-[12px] font-extrabold ring-1 ${toneClass}`}>
      <Icon name={icon} className="w-3.5 h-3.5" />
      <span>{label}</span>
      <span className="tabular-nums">{value.toLocaleString('fa-IR')}</span>
    </span>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Listing card                                                             */
/* ───────────────────────────────────────────────────────────────────────── */

function ListingCard({ l, delay = 0 }: { l: KindListing; delay?: number }) {
  const isNeed = l.type === 'need';
  const daysLeft = daysUntilExpiry(l.expiresAt);

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.4, delay }}
      className="group flex flex-col bg-white rounded-[26px] overflow-hidden isolate
                 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                 hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.22)]
                 hover:-translate-y-1 transition-all duration-300"
    >
      {/* Cover — fixed 16:10 box, never stretches */}
      <Link
        href={`/kindness-wall/${l.slug}`}
        className="relative aspect-[16/10] bg-ink-100 overflow-hidden block"
        aria-label={l.title}
      >
        {l.coverImage ? (
          <Image
            src={l.coverImage}
            alt={l.title}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover transition-transform duration-500 group-hover:scale-[1.06]"
          />
        ) : (
          <div className={`w-full h-full flex items-center justify-center
                           ${isNeed
                             ? 'bg-gradient-to-br from-rose-100 via-rose-50 to-white'
                             : 'bg-gradient-to-br from-mint-500/[0.18] via-brand-50 to-white'}`}>
            <Icon
              name={isNeed ? 'hand-heart' : 'helping-hand'}
              className={`w-16 h-16 ${isNeed ? 'text-rose-400' : 'text-brand-500'} opacity-80`}
            />
          </div>
        )}

        {/* Bottom scrim — keep type-pill legible on any cover */}
        <div aria-hidden="true"
             className="absolute inset-x-0 bottom-0 h-1/2 z-[1]
                        bg-gradient-to-t from-black/55 via-black/15 to-transparent" />

        {/* Type badge (top-right) — rose vs mint */}
        <span className={`absolute top-3 right-3 z-10 inline-flex items-center gap-1.5
                          h-8 px-3 rounded-2xl text-[11.5px] font-extrabold text-white
                          ring-[2.5px] ring-black/10
                          ${isNeed
                            ? 'bg-gradient-to-l from-[#f43f5e] to-[#e11d48] shadow-[0_4px_14px_-4px_rgba(225,29,72,.55)]'
                            : 'bg-gradient-to-l from-[#2FE0CC] to-[#1FB3A8] shadow-[0_4px_14px_-4px_rgba(37,197,186,.55)]'}`}>
          <Icon name={isNeed ? 'hand-heart' : 'helping-hand'} className="w-3.5 h-3.5" />
          {isNeed ? 'نیازمند کمک' : 'پیشنهاد کمک'}
        </span>

        {/* Expiry badge (top-left) — only when soon-to-expire */}
        {daysLeft !== null && daysLeft <= 7 && (
          <span className="absolute top-3 left-3 z-10 inline-flex items-center gap-1
                           h-7 px-2.5 rounded-full text-[11px] font-extrabold
                           bg-white/95 text-amber-700 backdrop-blur-md shadow-soft">
            <Icon name="clock" className="w-3 h-3" />
            {daysLeft === 0 ? 'امروز منقضی می‌شود' : `${daysLeft.toLocaleString('fa-IR')} روز تا انقضا`}
          </span>
        )}

        {/* Category chip (bottom-right) */}
        {l.categoryTitle && (
          <span className="absolute bottom-3 right-3 z-10 inline-flex items-center gap-1
                           h-6 px-2.5 rounded-full bg-white/95 text-ink-700
                           text-[11px] font-extrabold backdrop-blur-md shadow-soft">
            <Icon name="tag" className="w-3 h-3" />
            {l.categoryTitle}
          </span>
        )}

        {/* Matches affordance — only when there are smart matches */}
        {typeof l.matchesCount === 'number' && l.matchesCount > 0 && (
          <span className="absolute bottom-3 left-3 z-10 inline-flex items-center gap-1
                           h-6 px-2.5 rounded-full bg-brand-500 text-white
                           text-[11px] font-extrabold shadow-[0_4px_14px_-4px_rgba(13,128,116,.55)]">
            <Icon name="sparkles" className="w-3 h-3" />
            {l.matchesCount.toLocaleString('fa-IR')} مرتبط
          </span>
        )}
      </Link>

      {/* Body */}
      <div className="flex flex-col flex-1 p-4 md:p-4.5">
        <Link href={`/kindness-wall/${l.slug}`}
              className="font-extrabold text-[15px] text-ink-900 leading-7 line-clamp-2 min-h-[3.5rem]
                         hover:text-brand-600 transition-colors">
          {l.title}
        </Link>

        {/* Location + time */}
        <div className="mt-3 flex items-center justify-between text-[12px] text-ink-500 font-bold">
          <span className="inline-flex items-center gap-1">
            <Icon name="map-pin" className="w-3.5 h-3.5 text-brand-500" />
            <span className="truncate">
              {[l.city, l.province].filter(Boolean).join('، ') || 'سراسر کشور'}
            </span>
          </span>
          <span className="inline-flex items-center gap-1 shrink-0">
            <Icon name="clock" className="w-3.5 h-3.5" />
            {relativeTime(l.publishedAt)}
          </span>
        </div>

        {/* Owner + view */}
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

        {/* Action row — view (primary) + bookmark + share */}
        <div className="mt-3.5 flex items-center gap-2">
          <Link
            href={`/kindness-wall/${l.slug}`}
            className={`flex-1 inline-flex items-center justify-center gap-1.5 h-10 rounded-xl
                        text-white text-[13px] font-extrabold transition-all
                        ${isNeed
                          ? 'bg-gradient-to-l from-[#f43f5e] to-[#e11d48] hover:from-[#e11d48] hover:to-[#be123c] shadow-[0_6px_14px_-6px_rgba(225,29,72,.55)]'
                          : 'bg-gradient-to-l from-brand-500 to-brand-700 hover:from-brand-600 hover:to-brand-800 shadow-[0_6px_14px_-6px_rgba(13,128,116,.55)]'}`}
          >
            <span>{isNeed ? 'حمایت می‌کنم' : 'تماس می‌گیرم'}</span>
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
