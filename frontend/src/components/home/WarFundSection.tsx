'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { SectionTitle } from './SectionTitle';
import { formatPersianNumber } from '@/lib/utils';

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
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Atoms                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

/** Meta pill — three anchored slots so the number always lands dead-centre.
 *
 *   [ label (right) ]   [ number (centre) ]   [ unit (left) ]
 *
 * Label is absolute-positioned on the RTL-start (right) edge, unit is
 * absolute-positioned on the LTR-start (left) edge, and the numeric value
 * is absolutely centred via translate(-50%, -50%). This guarantees the
 * number visually sits in the middle of the pill regardless of how short
 * or long the label/unit text is — matching the designer's mockup exactly.
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
      className="relative h-[40px] rounded-[10px] border border-ink-200 bg-white"
    >
      {/* Label — RTL-start (right) */}
      <span
        className="absolute right-3.5 top-1/2 -translate-y-1/2
                   text-[12px] text-ink-500 font-medium leading-none z-[2]
                   bg-white px-1"
      >
        {label}
      </span>

      {/* Value — perfectly centred inside the pill */}
      <span
        className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
                    font-extrabold text-[13.5px] text-ink-900 whitespace-nowrap
                    max-w-[calc(100%-7rem)] overflow-hidden text-ellipsis
                    ${emphasis === 'num' ? 'tabular-nums' : ''}`}
      >
        {typeof value === 'number' ? formatPersianNumber(value) : value}
      </span>

      {/* Unit — LTR-start (left), only when provided */}
      {unit && (
        <span
          className="absolute left-3.5 top-1/2 -translate-y-1/2
                     text-[11px] text-ink-400 font-medium leading-none z-[2]
                     bg-white px-1"
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

function Card({ c, delay = 0 }: { c: CampaignCard; delay?: number }) {
  // UI displays Rial; backend stores Toman → ×10 at render time.
  const totalRial = c.totalAmount * 10;
  const pct = Math.round(c.progressPercent);

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
          <div className="flex flex-col items-center shrink-0 w-[120px] md:w-[130px]">
            <Link
              href={`/madadkar/${c.slug}`}
              className="relative w-full aspect-square rounded-[14px] overflow-hidden
                         ring-1 ring-ink-100 bg-ink-50"
            >
              {c.coverUrl ? (
                <Image
                  src={c.coverUrl}
                  alt={c.title}
                  fill
                  sizes="(min-width: 768px) 130px, 120px"
                  className="object-cover transition-transform duration-500 group-hover:scale-105"
                />
              ) : (
                <CoverFallback toneFrom={c.toneFrom} toneTo={c.toneTo} />
              )}
            </Link>

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

export function WarFundSection({ campaigns }: { campaigns: CampaignCard[] }) {
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

        {/* Pager arrows — using the designer's PNG assets */}
        <div className="flex items-center justify-center gap-4 mt-10">
          <button
            type="button"
            aria-label="قبلی"
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200"
          >
            <Image
              src="/brand/pager-arrow-prev.png"
              alt=""
              fill
              sizes="48px"
              className="object-contain"
            />
          </button>
          <button
            type="button"
            aria-label="بعدی"
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200"
          >
            <Image
              src="/brand/pager-arrow-next.png"
              alt=""
              fill
              sizes="48px"
              className="object-contain"
            />
          </button>
        </div>
      </div>
    </section>
  );
}
