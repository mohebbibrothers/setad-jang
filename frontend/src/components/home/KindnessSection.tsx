'use client';

import Link from 'next/link';
import { useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, Megaphone, HandHelping, Search } from 'lucide-react';
import { SectionTitle } from './SectionTitle';

/**
 * Backend contract (apps/kindness_wall):
 *   GET /api/v1/kindness-wall/listings/?listing_type=need|offer
 * Each listing: slug, title, listing_type, city, category_name, ...
 */
export type KindListing = {
  slug: string;
  title: string;
  type: 'need' | 'offer' | 'all';
};

const TABS = [
  { key: 'all',   label: 'همه آگهی‌های دیوار مهربانی', Icon: Megaphone },
  { key: 'offer', label: 'می‌خوام کمک کنم',           Icon: HandHelping },
  { key: 'need',  label: 'نیاز به کمک دارم',          Icon: Search },
] as const;

export function KindnessSection({ listings }: { listings: KindListing[] }) {
  const [active, setActive] = useState<(typeof TABS)[number]['key']>('all');

  const filtered = listings.filter((l) => active === 'all' || l.type === active);

  return (
    <section className="section-y bg-white" id="kindness">
      <div className="container-edge">
        <SectionTitle
          title="دیوار مهربانی"
          description="آگهی نیاز و کمک، بدون خرید و فروش، با هم‌تطبیق هوشمند جغرافیایی برای ارتباط سریع."
        />

        {/* Tabs (right→left) */}
        <div role="tablist" className="flex items-center justify-center gap-1
                                       border-b border-ink-100 mb-6 overflow-x-auto no-scrollbar">
          {TABS.map((t) => {
            const isActive = active === t.key;
            return (
              <button
                key={t.key}
                role="tab"
                aria-selected={isActive}
                onClick={() => setActive(t.key)}
                className={`relative inline-flex items-center gap-2 px-4 md:px-6 py-3 text-[14px] md:text-[15px]
                            font-semibold whitespace-nowrap transition-colors ${
                              isActive ? 'text-brand-600' : 'text-ink-500 hover:text-ink-800'
                            }`}
              >
                <t.Icon className="w-4 h-4" />
                {t.label}
                {isActive && (
                  <motion.span layoutId="kind-tab" className="absolute inset-x-2 -bottom-px h-[3px] rounded-full bg-brand-500" />
                )}
              </button>
            );
          })}
        </div>

        {/* Chip list — designer rendered listings as full-width pills */}
        <div className="bg-ink-50/50 rounded-2xl p-4 md:p-6 border border-ink-100">
          <div className="flex flex-wrap justify-center gap-2.5">
            {filtered.map((l, i) => (
              <motion.div
                key={l.slug}
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.3, delay: i * 0.04 }}
              >
                <Link
                  href={`/kindness-wall/${l.slug}`}
                  className="inline-flex items-center h-11 px-5 rounded-full
                             bg-brand-600 hover:bg-brand-700 text-white text-[13.5px] font-medium
                             transition-colors shadow-soft"
                >
                  {l.title}
                </Link>
              </motion.div>
            ))}
            {filtered.length === 0 && (
              <p className="text-ink-500 text-sm py-6">آگهی‌ای در این دسته یافت نشد.</p>
            )}
          </div>
        </div>

        {/* "+ جدید" CTA */}
        <div className="flex justify-center mt-7">
          <Link
            href="/kindness-wall/new"
            className="inline-flex items-center gap-2 h-12 px-8 rounded-full
                       bg-mint-500 hover:bg-mint-600 text-white font-bold shadow-soft transition-colors"
          >
            <Plus className="w-4 h-4" />
            جدید
          </Link>
        </div>
      </div>
    </section>
  );
}
