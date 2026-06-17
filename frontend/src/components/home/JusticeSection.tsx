'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Scale } from 'lucide-react';
import { SectionTitle } from './SectionTitle';

/**
 * Backend contract (apps/r4j):
 *   GET /api/v1/r4j/criminals/   → list (slug, full_name, role, image_url, ...)
 */
export type CriminalCard = {
  slug: string;
  fullName: string;
  pillLabel?: string;        // e.g. "مشارکت در مجازات"
  imageUrl?: string;
};

export function JusticeSection({ criminals }: { criminals: CriminalCard[] }) {
  return (
    <section className="section-y bg-white" id="justice">
      <div className="container-edge">
        <SectionTitle
          title="جایزه‌ای برای عدالت"
          description="بانک اطلاعاتی جنایتکاران و مجرمان بین‌المللی؛ مشارکت مردمی در مسیر تحقق عدالت."
        />

        {/* Outer white panel with subtle shadow & rounded corners */}
        <div className="bg-ink-50/60 rounded-[2rem] md:rounded-[2.5rem] p-4 md:p-8 lg:p-10
                        border border-ink-100">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-5">
            {criminals.slice(0, 7).map((p, i) => (
              <motion.article
                key={p.slug}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.07 }}
                className="bg-white rounded-2xl overflow-hidden shadow-soft hover:shadow-card
                           hover:-translate-y-0.5 transition-all duration-300 group"
              >
                <Link href={`/r4j/${p.slug}`} className="block">
                  <div className="relative aspect-[3/4] bg-ink-200 overflow-hidden">
                    {p.imageUrl ? (
                      <Image
                        src={p.imageUrl}
                        alt={p.fullName}
                        fill
                        sizes="(max-width: 768px) 50vw, 25vw"
                        className="object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                    ) : (
                      <div className="w-full h-full bg-gradient-to-br from-ink-300 to-ink-500 flex items-center justify-center text-white/40 text-6xl font-bold">
                        ?
                      </div>
                    )}
                    {/* Orange pill — "مشارکت در مجازات" */}
                    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 w-[88%]">
                      <div className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-full
                                      bg-accent-500 text-white text-[12px] font-bold shadow-soft">
                        <Scale className="w-3.5 h-3.5" />
                        {p.pillLabel || 'مشارکت در مجازات'}
                      </div>
                    </div>
                  </div>
                  <div className="px-3 py-3 bg-brand-500 text-white text-center text-sm font-semibold">
                    {p.fullName}
                  </div>
                </Link>
              </motion.article>
            ))}

            {/* Trophy CTA card (gold) */}
            <motion.article
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: 0.21 }}
              className="bg-gold-500 rounded-2xl shadow-soft relative overflow-hidden
                         flex flex-col items-center justify-between p-5 text-ink-900"
            >
              <div
                aria-hidden="true"
                className="absolute inset-0 opacity-[0.12] pointer-events-none"
                style={{
                  backgroundImage:
                    "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.8) 1px, transparent 1px)",
                  backgroundSize: '20px 20px',
                }}
              />
              <div className="relative flex-1 flex items-center justify-center w-full">
                <Image
                  src="/brand/trophy-gold.png"
                  alt="جایزه عدالت"
                  width={150}
                  height={214}
                  className="w-[100px] md:w-[120px] h-auto drop-shadow-[0_8px_16px_rgba(0,0,0,0.25)]"
                />
              </div>
              <div className="relative text-center w-full mt-3">
                <h3 className="text-base md:text-lg font-extrabold mb-2.5">جایزه عدالت</h3>
                <Link
                  href="/r4j"
                  className="inline-flex items-center justify-center w-full h-10 rounded-full
                             bg-white text-ink-900 text-[13px] font-bold hover:bg-ink-50 transition-colors"
                >
                  مشاهده همه جوایز
                </Link>
              </div>
            </motion.article>
          </div>

          {/* Bottom carousel arrows */}
          <div className="flex items-center justify-center gap-3 mt-6">
            <button aria-label="قبلی" className="w-9 h-9 rounded-full bg-white border border-ink-200
              hover:border-brand-300 hover:text-brand-600 text-ink-500 flex items-center justify-center transition-colors">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            <button aria-label="بعدی" className="w-9 h-9 rounded-full bg-white border border-ink-200
              hover:border-brand-300 hover:text-brand-600 text-ink-500 flex items-center justify-center transition-colors">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
