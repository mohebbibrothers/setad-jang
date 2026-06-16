'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { Users, Clock, Heart, ArrowLeft } from 'lucide-react';
import { formatPersianNumber, formatToman } from '@/lib/utils';

type Campaign = {
  slug: string;
  title: string;
  category: string;
  image: string;        // gradient placeholder for now
  raised: number;
  goal: number;
  donors: number;
  daysLeft: number;
  tone: 'brand' | 'rose' | 'amber' | 'violet';
};

const TONES: Record<Campaign['tone'], { from: string; to: string; chip: string }> = {
  brand:  { from: 'from-brand-500',  to: 'to-brand-700',   chip: 'bg-brand-50 text-brand-700' },
  rose:   { from: 'from-rose-500',   to: 'to-rose-700',    chip: 'bg-rose-50 text-rose-700' },
  amber:  { from: 'from-amber-500',  to: 'to-amber-700',   chip: 'bg-amber-50 text-amber-700' },
  violet: { from: 'from-violet-500', to: 'to-violet-700',  chip: 'bg-violet-50 text-violet-700' },
};

const SAMPLE: Campaign[] = [
  { slug: 'help-gaza-2026', title: 'یاری کودکان غزه — تأمین دارو و غذا', category: 'فلسطین', image: '', raised: 184_500_000, goal: 300_000_000, donors: 1284, daysLeft: 12, tone: 'rose' },
  { slug: 'school-rural-jangal', title: 'بازسازی مدرسه روستایی جنگل', category: 'آموزش', image: '', raised: 62_300_000, goal: 120_000_000, donors: 412, daysLeft: 24, tone: 'amber' },
  { slug: 'jihadi-medical-camp', title: 'اردوی جهادی پزشکی منطقه محروم', category: 'سلامت', image: '', raised: 95_800_000, goal: 150_000_000, donors: 698, daysLeft: 7, tone: 'brand' },
  { slug: 'orphan-monthly', title: 'پشتیبانی ماهانه از ایتام', category: 'مددکاری', image: '', raised: 47_900_000, goal: 90_000_000, donors: 305, daysLeft: 30, tone: 'violet' },
];

function ProgressBar({ value, tone }: { value: number; tone: Campaign['tone'] }) {
  const t = TONES[tone];
  return (
    <div className="w-full h-2.5 rounded-full bg-ink-100 overflow-hidden">
      <motion.div
        initial={{ width: 0 }}
        whileInView={{ width: `${Math.min(100, value)}%` }}
        viewport={{ once: true }}
        transition={{ duration: 1, ease: 'easeOut' }}
        className={`h-full rounded-full bg-gradient-to-l ${t.from} ${t.to}`}
      />
    </div>
  );
}

export function CampaignsTeaser() {
  return (
    <section className="section-y bg-surface-muted">
      <div className="container-edge">
        <div className="flex items-end justify-between gap-6 mb-10">
          <div>
            <span className="eyebrow">کمپین‌های فعال مددکاری</span>
            <h2 className="mt-4 text-3xl md:text-4xl font-extrabold text-ink-900">
              با هم، تفاوت ایجاد می‌کنیم
            </h2>
            <p className="mt-3 text-ink-600 max-w-xl leading-8">
              کمپین‌هایی که همین حالا نیازمند مشارکت شما هستند.
              مشارکت سهم‌محور، شفاف و قابل پیگیری.
            </p>
          </div>
          <Link href="/madadkar" className="hidden md:inline-flex btn-outline btn-md">
            مشاهده همه کمپین‌ها
            <ArrowLeft className="w-4 h-4" />
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {SAMPLE.map((c, i) => {
            const t = TONES[c.tone];
            const pct = Math.round((c.raised / c.goal) * 100);
            return (
              <motion.article
                key={c.slug}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.45, delay: i * 0.06 }}
                className="card overflow-hidden flex flex-col"
              >
                <Link href={`/madadkar/${c.slug}`} className="block">
                  <div className={`relative aspect-[16/10] bg-gradient-to-br ${t.from} ${t.to} overflow-hidden`}>
                    <div className="absolute inset-0 bg-grid-pattern opacity-30" />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Heart className="w-20 h-20 text-white/30" strokeWidth={1.2} />
                    </div>
                    <span className={`absolute top-3 right-3 text-xs font-semibold px-2.5 py-1 rounded-full bg-white/95 ${t.chip.split(' ')[1]}`}>
                      {c.category}
                    </span>
                  </div>
                </Link>

                <div className="p-5 flex flex-col flex-1">
                  <h3 className="text-[15.5px] font-bold text-ink-900 leading-7 line-clamp-2 min-h-[3.5rem]">
                    <Link href={`/madadkar/${c.slug}`} className="hover:text-brand-700 transition-colors">
                      {c.title}
                    </Link>
                  </h3>

                  <div className="mt-4">
                    <div className="flex justify-between items-baseline text-sm">
                      <span className="text-ink-500">پیشرفت</span>
                      <span className="font-bold text-ink-900 tabular-nums">{formatPersianNumber(pct)}%</span>
                    </div>
                    <div className="mt-2"><ProgressBar value={pct} tone={c.tone} /></div>
                    <div className="mt-2 flex justify-between text-xs text-ink-500">
                      <span>جمع‌آوری‌شده: <strong className="text-ink-800">{formatToman(c.raised)}</strong></span>
                      <span>هدف: {formatToman(c.goal)}</span>
                    </div>
                  </div>

                  <div className="mt-4 pt-4 border-t border-ink-100 flex items-center justify-between text-xs text-ink-500">
                    <span className="inline-flex items-center gap-1.5"><Users className="w-4 h-4" /> {formatPersianNumber(c.donors)} نفر</span>
                    <span className="inline-flex items-center gap-1.5"><Clock className="w-4 h-4" /> {formatPersianNumber(c.daysLeft)} روز مانده</span>
                  </div>

                  <Link
                    href={`/madadkar/${c.slug}`}
                    className="btn-primary btn-md mt-5"
                  >
                    مشارکت در این کمپین
                  </Link>
                </div>
              </motion.article>
            );
          })}
        </div>

        <div className="mt-8 md:hidden text-center">
          <Link href="/madadkar" className="btn-outline btn-md">
            مشاهده همه کمپین‌ها <ArrowLeft className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}
