'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { Icon } from '@/components/icons/Icon';

/**
 * Backend contract (apps/kindness_wall):
 *   GET /api/v1/kindness-wall/categories/
 *   GET /api/v1/kindness-wall/listings/?listing_type=need|offer&category=…
 *
 * Listing fields used (from KindnessListingListSerializer):
 *   id, slug, listing_type, category{title, icon}, title,
 *   province, city, district, owner_full_name_snapshot,
 *   owner_avatar_snapshot, published_at, expires_at,
 *   view_count, cover_image
 */
export type KindListing = {
  slug: string;
  title: string;
  type: 'need' | 'offer';
  categoryTitle?: string;
  province?: string;
  city?: string;
  district?: string;
  ownerName?: string;
  ownerAvatar?: string;
  coverImage?: string;
  publishedAt?: string;
  expiresAt?: string;
  viewCount?: number;
};

const FILTERS = [
  { key: 'all',   label: 'همه آگهی‌ها',         icon: 'megaphone'     as const },
  { key: 'offer', label: 'می‌خواهم کمک کنم',    icon: 'helping-hand'  as const },
  { key: 'need',  label: 'نیاز به کمک دارم',    icon: 'hand-heart'    as const },
] as const;

type FilterKey = (typeof FILTERS)[number]['key'];

function relativeTime(dateStr?: string): string {
  if (!dateStr) return 'به‌تازگی';
  const d = new Date(dateStr);
  const diffMs = Date.now() - d.getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 60) return `${m} دقیقه پیش`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} ساعت پیش`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days} روز پیش`;
  const months = Math.floor(days / 30);
  return `${months} ماه پیش`;
}

export function KindnessSection({ listings }: { listings: KindListing[] }) {
  const [filter, setFilter] = useState<FilterKey>('all');

  const visible = useMemo(
    () => listings.filter((l) => filter === 'all' || l.type === filter).slice(0, 6),
    [listings, filter],
  );

  // Stats for the section header pills (calculated from the live list)
  const counts = useMemo(
    () => ({
      all:   listings.length,
      need:  listings.filter((l) => l.type === 'need').length,
      offer: listings.filter((l) => l.type === 'offer').length,
    }),
    [listings],
  );

  return (
    <section className="section-y bg-white" id="kindness">
      <div className="container-edge">
        <SectionTitle
          title="دیوار مهربانی"
          description="جایی برای رساندن کمک‌های مردمی، بدون خرید و فروش. هم‌تطبیق هوشمند جغرافیایی، حفاظت از حریم خصوصی و افشای شماره تماس فقط برای کاربر تأییدشده."
        />

        {/* Filter tabs — designer style, animated underline */}
        <div role="tablist" aria-label="فیلتر آگهی‌ها"
             className="flex items-center justify-center gap-1 border-b border-ink-100 mb-8 overflow-x-auto no-scrollbar">
          {FILTERS.map((f) => {
            const active = filter === f.key;
            return (
              <button
                key={f.key}
                role="tab"
                aria-selected={active}
                onClick={() => setFilter(f.key)}
                className={`relative inline-flex items-center gap-2 px-4 md:px-6 py-3 text-[13.5px] md:text-[14.5px]
                            font-semibold whitespace-nowrap transition-colors ${
                              active ? 'text-brand-600' : 'text-ink-500 hover:text-ink-800'
                            }`}
              >
                <Icon name={f.icon} className="w-4 h-4" />
                <span>{f.label}</span>
                <span className={`inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5
                                  rounded-full text-[11px] font-bold tabular-nums ${
                                    active ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-500'
                                  }`}>
                  {counts[f.key].toLocaleString('fa-IR')}
                </span>
                {active && (
                  <motion.span
                    layoutId="kind-tab-underline"
                    className="absolute inset-x-2 -bottom-px h-[3px] rounded-full bg-brand-500"
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* Cards grid — real listing cards (3 cols desktop, 2 tablet, 1 mobile) */}
        <AnimatePresence mode="wait">
          <motion.div
            key={filter}
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
                <p className="text-ink-500">آگهی‌ای در این دسته یافت نشد.</p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        {/* Footer actions: see all + post new */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-10">
          <Link
            href="/kindness-wall"
            className="inline-flex items-center gap-2 h-12 px-7 rounded-full
                       bg-white border-2 border-brand-500 text-brand-700 font-bold text-[14px]
                       hover:bg-brand-50 transition-colors"
          >
            مشاهده همه آگهی‌ها
            <Icon name="arrow-left" className="w-4 h-4" />
          </Link>
          <Link
            href="/kindness-wall/new"
            className="inline-flex items-center gap-2 h-12 px-8 rounded-full
                       bg-mint-500 hover:bg-mint-600 text-white font-bold text-[14px]
                       shadow-soft transition-colors"
          >
            <Icon name="plus" className="w-4 h-4" strokeWidth={2.5} />
            ثبت آگهی جدید
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ──────────────────────────────────────────────────────────────────────── */

function ListingCard({ l, delay = 0 }: { l: KindListing; delay?: number }) {
  const isNeed = l.type === 'need';
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.4, delay }}
      className="group relative flex flex-col bg-white rounded-2xl border border-ink-100 overflow-hidden
                 shadow-soft hover:shadow-card hover:-translate-y-1 transition-all duration-300"
    >
      {/* Cover */}
      <Link href={`/kindness-wall/${l.slug}`} className="block relative aspect-[16/10] bg-ink-100 overflow-hidden">
        {l.coverImage ? (
          <Image
            src={l.coverImage}
            alt={l.title}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className={`w-full h-full flex items-center justify-center
                          ${isNeed
                            ? 'bg-gradient-to-br from-brand-50 to-brand-100'
                            : 'bg-gradient-to-br from-mint-500/15 to-brand-100'}`}>
            <Icon
              name={isNeed ? 'hand-heart' : 'helping-hand'}
              className={`w-16 h-16 ${isNeed ? 'text-brand-400' : 'text-mint-600'} opacity-70`}
            />
          </div>
        )}

        {/* Type badge */}
        <span className={`absolute top-3 right-3 inline-flex items-center gap-1.5 px-3 h-7 rounded-full
                          text-[11.5px] font-bold backdrop-blur-sm ${
                            isNeed
                              ? 'bg-rose-500/95 text-white'
                              : 'bg-mint-500/95 text-white'
                          }`}>
          <Icon name={isNeed ? 'hand-heart' : 'helping-hand'} className="w-3.5 h-3.5" />
          {isNeed ? 'نیازمند کمک' : 'پیشنهاد کمک'}
        </span>

        {/* Category chip */}
        {l.categoryTitle && (
          <span className="absolute bottom-3 right-3 inline-flex items-center px-2.5 h-6 rounded-full
                           bg-white/95 text-ink-700 text-[11px] font-semibold backdrop-blur-sm shadow-soft">
            <Icon name="tag" className="w-3 h-3 ml-1" />
            {l.categoryTitle}
          </span>
        )}
      </Link>

      {/* Body */}
      <div className="flex flex-col flex-1 p-4 md:p-5">
        <Link href={`/kindness-wall/${l.slug}`}
              className="font-bold text-[15px] text-ink-800 leading-7 line-clamp-2 min-h-[3.5rem]
                         hover:text-brand-600 transition-colors">
          {l.title}
        </Link>

        {/* Location + time */}
        <div className="mt-3 flex items-center justify-between text-[12.5px] text-ink-500">
          <span className="inline-flex items-center gap-1">
            <Icon name="map-pin" className="w-3.5 h-3.5" />
            {[l.city, l.province].filter(Boolean).join('، ') || 'سراسر کشور'}
          </span>
          <span className="inline-flex items-center gap-1">
            <Icon name="clock" className="w-3.5 h-3.5" />
            {relativeTime(l.publishedAt)}
          </span>
        </div>

        {/* Owner + view */}
        <div className="mt-4 pt-4 border-t border-ink-100 flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-8 h-8 rounded-full overflow-hidden bg-brand-50 flex items-center justify-center shrink-0">
              {l.ownerAvatar ? (
                <Image src={l.ownerAvatar} alt="" width={32} height={32} className="w-full h-full object-cover" />
              ) : (
                <Icon name="user" className="w-4 h-4 text-brand-500" />
              )}
            </div>
            <span className="text-[12.5px] text-ink-700 truncate">
              {l.ownerName || 'کاربر دیوار مهربانی'}
            </span>
          </div>
          {typeof l.viewCount === 'number' && (
            <span className="inline-flex items-center gap-1 text-[11.5px] text-ink-400 tabular-nums shrink-0">
              <Icon name="eye" className="w-3.5 h-3.5" />
              {l.viewCount.toLocaleString('fa-IR')}
            </span>
          )}
        </div>

        {/* Action row */}
        <div className="mt-4 flex items-center gap-2">
          <Link
            href={`/kindness-wall/${l.slug}`}
            className="flex-1 inline-flex items-center justify-center h-10 rounded-xl
                       bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-bold transition-colors"
          >
            مشاهده آگهی
          </Link>
          <button
            type="button"
            aria-label="نشان‌گذاری"
            className="w-10 h-10 rounded-xl border border-ink-200 text-ink-500
                       hover:border-rose-300 hover:text-rose-500 transition-colors
                       inline-flex items-center justify-center"
          >
            <Icon name="heart" className="w-4 h-4" />
          </button>
          <button
            type="button"
            aria-label="اشتراک‌گذاری"
            className="w-10 h-10 rounded-xl border border-ink-200 text-ink-500
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
