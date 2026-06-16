'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { HandHeart } from 'lucide-react';
import { SectionTitle } from './SectionTitle';
import { formatPersianNumber } from '@/lib/utils';

/**
 * Backend contract (matches apps/madadkar):
 *   GET /api/v1/madadkar/campaigns/   → list of campaign summaries
 * Fields used here (subset; backend may extend):
 *   - slug, title, sponsor_name, total_amount_rial,
 *     share_price_rial, shares_total, shares_remaining,
 *     cover_image_url, progress_percent
 */
export type CampaignCard = {
  slug: string;
  title: string;
  sponsor: string;
  totalAmount: number;        // rial
  sharePrice: number;         // rial
  sharesTotal: number;
  sharesRemaining: number;
  progressPercent: number;
  coverUrl?: string;
};

/**
 * Designer-faithful campaign card: a wide info card with title, a 3-row
 * meta table (amount/shares/sponsor), a thin teal progress bar, and a
 * full-width primary CTA. A small cover thumbnail sits on the right.
 */
function Card({ c, delay = 0 }: { c: CampaignCard; delay?: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.45, delay }}
      className="bg-white rounded-2xl border border-ink-100 shadow-soft hover:shadow-card
                 transition-all duration-300 overflow-hidden"
    >
      <div className="p-4 md:p-5">
        {/* Header row: title + thumbnail */}
        <div className="flex items-start gap-4 mb-4">
          <Link
            href={`/madadkar/${c.slug}`}
            className="flex-1 font-bold text-[14.5px] md:text-[15px] text-ink-800 leading-7
                       line-clamp-2 hover:text-brand-600 transition-colors"
          >
            {c.title}
          </Link>
          <div className="relative shrink-0 w-[88px] h-[72px] rounded-xl overflow-hidden bg-ink-100">
            {c.coverUrl ? (
              <Image
                src={c.coverUrl}
                alt={c.title}
                fill
                sizes="88px"
                className="object-cover"
              />
            ) : (
              <div className="w-full h-full bg-gradient-to-br from-brand-100 to-brand-50 flex items-center justify-center">
                <HandHeart className="w-7 h-7 text-brand-500" />
              </div>
            )}
          </div>
        </div>

        {/* Meta table — 3 rows in pill inputs (matches mockup) */}
        <div className="space-y-2 mb-3">
          <MetaRow label="مبلغ کل" valueLabel="ریال" value={c.totalAmount} />
          <div className="grid grid-cols-2 gap-2">
            <MetaRow label="باقی‌مانده" valueLabel="سهم" value={c.sharesRemaining} compact />
            <MetaRow label="تعداد سهم" valueLabel="سهم" value={c.sharesTotal} compact />
          </div>
          <MetaRowText label="مددکار" value={c.sponsor} />
        </div>

        {/* Thin progress bar */}
        <div className="flex items-center gap-3 mb-4">
          <span className="text-xs font-semibold text-ink-600 tabular-nums shrink-0">
            ٪{formatPersianNumber(c.progressPercent)}
          </span>
          <div className="flex-1 h-1.5 rounded-full bg-ink-100 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${c.progressPercent}%` }}
              viewport={{ once: true }}
              transition={{ duration: 1.1, ease: 'easeOut' }}
              className="h-full bg-brand-500 rounded-full"
            />
          </div>
        </div>

        {/* CTA */}
        <Link
          href={`/madadkar/${c.slug}/participate`}
          className="inline-flex items-center justify-center gap-2 w-full h-11
                     rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-[14.5px] font-bold
                     transition-colors"
        >
          <HandHeart className="w-4 h-4" />
          مدد به حرکت
        </Link>
      </div>
    </motion.article>
  );
}

function MetaRow({
  label, value, valueLabel, compact = false,
}: { label: string; value: number; valueLabel: string; compact?: boolean }) {
  return (
    <div className={`flex items-center justify-between gap-2 h-${compact ? '9' : '10'} px-3
                     rounded-lg border border-ink-200/70 bg-white`}>
      <span className="text-[12px] text-ink-500">{label}</span>
      <div className="flex items-center gap-2 min-w-0">
        <span className="font-bold text-[13px] text-ink-800 tabular-nums truncate">
          {formatPersianNumber(value)}
        </span>
        <span className="text-[11px] text-ink-400 shrink-0">{valueLabel}</span>
      </div>
    </div>
  );
}

function MetaRowText({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 h-10 px-3 rounded-lg border border-ink-200/70 bg-white">
      <span className="text-[12px] text-ink-500">{label}</span>
      <span className="font-bold text-[13px] text-ink-800 truncate">{value}</span>
    </div>
  );
}

export function WarFundSection({ campaigns }: { campaigns: CampaignCard[] }) {
  return (
    <section className="section-y bg-white" id="warfund">
      <div className="container-edge">
        <SectionTitle
          title="پشتیبانی مالی جنگ"
          description="مشارکت سهم‌محور، شفاف و قابل پیگیری در کمپین‌های پشتیبانی از مدافعان و جبهه مقاومت."
        />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {campaigns.map((c, i) => (
            <Card key={c.slug} c={c} delay={i * 0.06} />
          ))}
        </div>

        {/* Pager arrows + view-all (designer style) */}
        <div className="flex items-center justify-center gap-3 mt-8">
          <button
            aria-label="قبلی"
            className="w-10 h-10 rounded-full bg-white border border-ink-200 hover:border-brand-300
                       hover:text-brand-600 text-ink-500 flex items-center justify-center transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          <Link
            href="/madadkar"
            className="px-5 h-10 inline-flex items-center rounded-full bg-brand-50 text-brand-700 text-sm font-semibold
                       hover:bg-brand-100 transition-colors"
          >
            مشاهده همه کمپین‌ها
          </Link>
          <button
            aria-label="بعدی"
            className="w-10 h-10 rounded-full bg-white border border-ink-200 hover:border-brand-300
                       hover:text-brand-600 text-ink-500 flex items-center justify-center transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    </section>
  );
}
