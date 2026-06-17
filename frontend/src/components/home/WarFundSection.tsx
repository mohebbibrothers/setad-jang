'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { formatPersianNumber } from '@/lib/utils';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * War-fund (Madadkar) campaign card — designer-faithful (v2).
 *
 * Backend contract (apps/madadkar):
 *   GET /api/v1/madadkar/campaigns/   → CampaignPublicListSerializer
 *
 * Fields used here (subset; full contract in serializers.py):
 *   id, sponsor{id,name,slug,logo}, title, slug, cover_image,
 *   total_amount, total_shares, share_price,
 *   purchased_shares, purchased_amount, participant_count,
 *   remaining_shares, progress_percent, is_fully_funded,
 *   status, has_deadline, deadline, published_at, completed_at, closed_at
 *
 * Display notes:
 *   - Backend stores monetary fields in TOMAN; we display in RIAL (×10)
 *     to match the designer's mockup ("۱۰،۰۰۰،۰۰۰،۰۰۰ ریال").
 *   - share_price = total_amount / total_shares (computed in model.save()).
 *   - remaining_shares & progress_percent are `@property` on Campaign.
 * ───────────────────────────────────────────────────────────────────────────
 */
export type CampaignCard = {
  slug: string;
  title: string;
  sponsor: string;
  /** Toman; UI multiplies by 10 to render Rial as designer specified */
  totalAmount: number;
  /** Toman per share */
  sharePrice: number;
  sharesTotal: number;
  sharesRemaining: number;
  progressPercent: number;
  coverUrl?: string;
  /** Optional palette hint when no cover image is provided (graceful fallback) */
  toneFrom?: string;
  toneTo?: string;
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Atoms                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

function MetaPill({
  label,
  value,
  unit,
  emphasis = 'num',
}: {
  label: string;
  value: string | number;
  unit?: string;
  /** "num" right-aligns a tabular number; "text" right-aligns a label */
  emphasis?: 'num' | 'text';
}) {
  return (
    <div
      className="flex items-center justify-between gap-2 h-[40px] px-3.5
                 rounded-[10px] border border-ink-200 bg-white"
    >
      <span className="text-[12px] text-ink-500 font-medium shrink-0">{label}</span>
      <div className="flex items-baseline gap-1.5 min-w-0">
        <span
          className={`font-extrabold text-[13.5px] text-ink-900 truncate
                      ${emphasis === 'num' ? 'tabular-nums' : ''}`}
        >
          {typeof value === 'number' ? formatPersianNumber(value) : value}
        </span>
        {unit && (
          <span className="text-[11px] text-ink-400 font-medium shrink-0">{unit}</span>
        )}
      </div>
    </div>
  );
}

/** Hand-of-help icon — matches the small palm glyph on the CTA in the mockup */
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

/** Fallback cover: gradient + subtle dotted texture (no awkward big logo) */
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
      <HandIcon className="absolute inset-0 m-auto w-9 h-9 text-white/85" />
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Card                                                                     */
/* ───────────────────────────────────────────────────────────────────────── */

function Card({ c, delay = 0 }: { c: CampaignCard; delay?: number }) {
  // UI shows Rial; storage is Toman → multiply by 10.
  const totalRial = c.totalAmount * 10;

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
        {/* ── Header: title (right) + cover thumbnail (left) ───────────── */}
        <div className="flex items-start gap-3.5 mb-4">
          <Link
            href={`/madadkar/${c.slug}`}
            className="flex-1 font-extrabold text-[14.5px] md:text-[15px] text-ink-900 leading-7
                       line-clamp-2 hover:text-brand-600 transition-colors min-h-[3.5rem]"
          >
            {c.title}
          </Link>
          <div
            className="relative shrink-0 w-[96px] h-[80px] rounded-[12px] overflow-hidden
                       ring-1 ring-ink-100 bg-ink-50"
          >
            {c.coverUrl ? (
              <Image
                src={c.coverUrl}
                alt={c.title}
                fill
                sizes="96px"
                className="object-cover transition-transform duration-500 group-hover:scale-105"
              />
            ) : (
              <CoverFallback toneFrom={c.toneFrom} toneTo={c.toneTo} />
            )}
          </div>
        </div>

        {/* ── Meta pills: 3 rows (matches mockup) ──────────────────────── */}
        <div className="space-y-2 mb-3.5">
          <MetaPill label="مبلغ کل" value={totalRial} unit="ریال" />

          <div className="grid grid-cols-2 gap-2">
            <MetaPill label="باقی‌مانده" value={c.sharesRemaining} unit="سهم" />
            <MetaPill label="تعداد سهم" value={c.sharesTotal} unit="سهم" />
          </div>

          <MetaPill label="مددکار" value={c.sponsor} emphasis="text" />
        </div>

        {/* ── Progress bar: tiny pct on the LEFT, bar fills to the RIGHT ── */}
        <div className="flex items-center gap-3 mb-4">
          <span className="text-[11.5px] font-extrabold text-ink-700 tabular-nums shrink-0">
            ٪{formatPersianNumber(Math.round(c.progressPercent))}
          </span>
          <div className="flex-1 h-[6px] rounded-full bg-ink-100 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${c.progressPercent}%` }}
              viewport={{ once: true }}
              transition={{ duration: 1.1, ease: 'easeOut' }}
              className="h-full rounded-full bg-gradient-to-l from-brand-400 to-brand-600"
            />
          </div>
        </div>

        {/* ── CTA: full-width primary brand button ─────────────────────── */}
        <Link
          href={`/madadkar/${c.slug}/participate`}
          className="relative inline-flex items-center justify-center gap-2 w-full h-[46px]
                     rounded-[12px] bg-brand-500 hover:bg-brand-600 active:bg-brand-700
                     text-white text-[14.5px] font-extrabold
                     shadow-[0_6px_14px_-6px_rgba(13,128,116,.55)]
                     transition-colors overflow-hidden"
        >
          <HandIcon />
          <span>مدد به حرکت</span>
          {/* Subtle shimmer on hover */}
          <span
            aria-hidden="true"
            className="absolute inset-0 -translate-x-full group-hover:translate-x-full
                       transition-transform duration-[1100ms] ease-out
                       bg-gradient-to-l from-transparent via-white/15 to-transparent"
          />
        </Link>
      </div>
    </motion.article>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function WarFundSection({ campaigns }: { campaigns: CampaignCard[] }) {
  // 2 rows of 2 cards on desktop matches the mockup exactly
  const visible = campaigns.slice(0, 4);

  return (
    <section className="section-y bg-white" id="warfund">
      <div className="container-edge">
        <SectionTitle
          title="پشتیبانی مالی جنگ"
          description="مشارکت سهم‌محور، شفاف و قابل پیگیری در کمپین‌های پشتیبانی از مدافعان و جبهه مقاومت."
        />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
          {visible.map((c, i) => (
            <Card key={c.slug} c={c} delay={i * 0.06} />
          ))}
        </div>

        {/* Pager (designer style — just the two pill-arrows, centred) */}
        <div className="flex items-center justify-center gap-3 mt-8">
          <button
            aria-label="قبلی"
            className="group/btn inline-flex items-center justify-center gap-1
                       h-9 px-3.5 rounded-full bg-white border border-ink-200
                       text-ink-500 hover:border-brand-300 hover:text-brand-600
                       transition-colors"
          >
            <span className="text-[11px] tracking-[2px] opacity-70">— —</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <Link
            href="/madadkar"
            className="px-5 h-9 inline-flex items-center rounded-full bg-brand-50 text-brand-700
                       text-[13px] font-bold hover:bg-brand-100 transition-colors"
          >
            مشاهده همه کمپین‌ها
          </Link>
          <button
            aria-label="بعدی"
            className="group/btn inline-flex items-center justify-center gap-1
                       h-9 px-3.5 rounded-full bg-white border border-ink-200
                       text-ink-500 hover:border-brand-300 hover:text-brand-600
                       transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="text-[11px] tracking-[2px] opacity-70">— —</span>
          </button>
        </div>
      </div>
    </section>
  );
}
