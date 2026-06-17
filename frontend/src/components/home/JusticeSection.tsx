'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Justice / R4J section — designer-faithful (v2).
 *
 * Backend contract (apps/r4j):
 *   GET /api/v1/r4j/criminals/  → R4JPublicCriminalListSerializer
 * Fields used here:
 *   id, slug, first_name, last_name, country, province, city,
 *   primary_photo{url,…}, total_bounty_toman, bounties_count
 *
 * Layout (matches the designer's mockup exactly):
 *   - A single ROW of FOUR cards inside an off-white panel:
 *       [criminal] [criminal] [criminal] [GOLD TROPHY CTA]
 *   - More criminals are reachable via the bottom pager arrows
 *     (the same PNG glyphs that drive the WarFund carousel).
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐  │
 *   │  │  photo  │  │  photo  │  │  photo  │  │     🏆 trophy   │  │
 *   │  │  [pill] │  │  [pill] │  │  [pill] │  │   جایزه عدالت   │  │
 *   │  │  name   │  │  name   │  │  name   │  │ [مشاهده همه]    │  │
 *   │  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘  │
 *   └──────────────────────────────────────────────────────────────┘
 *                      ◀── ──▶   ← designer pager arrows
 *
 *   - Orange pill carries a tiny GAVEL glyph (mockup) — not a scale.
 *   - Each criminal page card has the photo as a full bleed, a green
 *     name plate at the bottom, and the pill anchored above the plate.
 * ───────────────────────────────────────────────────────────────────────────
 */
export type CriminalCard = {
  slug: string;
  fullName: string;
  pillLabel?: string;        // default: 'مشارکت در مجازات'
  imageUrl?: string;
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Icons                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

/** Judge's gavel glyph — matches the icon inside the mockup's orange pill */
function GavelIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="m14.5 12.5-8 8a2.119 2.119 0 1 1-3-3l8-8" />
      <path d="m16 16 6-6" />
      <path d="m8 8 6-6" />
      <path d="m9 7 8 8" />
      <path d="m21 11-8-8" />
    </svg>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Atoms                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

function CriminalCardView({ p, delay = 0 }: { p: CriminalCard; delay?: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.4, delay }}
      className="bg-white rounded-2xl overflow-hidden
                 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                 hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.22)]
                 hover:-translate-y-0.5 transition-all duration-300 group
                 flex flex-col"
    >
      <Link href={`/r4j/${p.slug}`} className="flex flex-col">
        {/* Photo */}
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
            <div
              className="w-full h-full bg-gradient-to-br from-ink-300 to-ink-500
                         flex items-center justify-center text-white/40 text-6xl font-extrabold"
            >
              ?
            </div>
          )}

          {/* Orange action pill — anchored just above the green name plate */}
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 w-[88%]">
            <div
              className="flex items-center justify-center gap-1.5 px-3 h-8 rounded-full
                         bg-accent-500 text-white text-[12px] font-extrabold
                         shadow-[0_4px_12px_-4px_rgba(229,82,20,.5)]
                         hover:bg-accent-600 transition-colors"
            >
              <GavelIcon className="w-3.5 h-3.5" />
              <span>{p.pillLabel || 'مشارکت در مجازات'}</span>
            </div>
          </div>
        </div>

        {/* Green name plate */}
        <div
          className="px-3 py-3 bg-brand-500 text-white text-center
                     text-[14px] md:text-[14.5px] font-extrabold"
        >
          {p.fullName}
        </div>
      </Link>
    </motion.article>
  );
}

function TrophyCard() {
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, delay: 0.18 }}
      className="bg-gold-500 rounded-2xl
                 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                 relative overflow-hidden flex flex-col items-center
                 justify-between p-5 text-ink-900"
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.12] pointer-events-none"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.85) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      />
      <div className="relative flex-1 flex items-center justify-center w-full pt-2">
        <Image
          src="/brand/trophy-gold.png"
          alt="جایزه عدالت"
          width={180}
          height={260}
          className="w-[120px] md:w-[150px] h-auto drop-shadow-[0_10px_18px_rgba(0,0,0,0.28)]"
        />
      </div>
      <div className="relative text-center w-full mt-3">
        <h3 className="text-lg md:text-xl font-extrabold mb-3">جایزه عدالت</h3>
        <Link
          href="/r4j"
          className="inline-flex items-center justify-center w-full h-11 rounded-full
                     bg-white text-ink-900 text-[13.5px] font-extrabold
                     hover:bg-ink-50 active:scale-[.98] transition-all"
        >
          مشاهده همه جوایز
        </Link>
      </div>
    </motion.article>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function JusticeSection({ criminals }: { criminals: CriminalCard[] }) {
  // 3 criminals + 1 trophy per page → exactly the row drawn by the designer
  const PAGE_SIZE = 3;
  const totalPages = Math.max(1, Math.ceil(criminals.length / PAGE_SIZE));
  const [page, setPage] = useState(0);
  const visible = useMemo(
    () => criminals.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [criminals, page],
  );

  const prev = () => setPage((p) => (p - 1 + totalPages) % totalPages);
  const next = () => setPage((p) => (p + 1) % totalPages);

  return (
    <section className="section-y bg-white" id="justice">
      <div className="container-edge">
        <SectionTitle
          title="جایزه‌ای برای عدالت"
          description="بانک اطلاعاتی جنایتکاران و مجرمان بین‌المللی؛ مشارکت مردمی در مسیر تحقق عدالت."
        />

        {/* Off-white outer panel */}
        <div
          className="bg-ink-50/60 rounded-[2rem] md:rounded-[2.5rem]
                     p-4 md:p-8 lg:p-10 border border-ink-100"
        >
          {/* ONE row of 4 cards — three criminals + the gold trophy CTA */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-5">
            <AnimatePresence mode="wait" initial={false}>
              {visible.map((p, i) => (
                <CriminalCardView key={`${page}-${p.slug}`} p={p} delay={i * 0.07} />
              ))}
            </AnimatePresence>
            <TrophyCard />
          </div>
        </div>

        {/* Pager (same PNG arrows as the WarFund carousel) */}
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
            onClick={next}
            disabled={totalPages <= 1}
            className="relative w-12 h-12 rounded-full hover:scale-110 active:scale-95
                       transition-transform duration-200 disabled:opacity-40
                       disabled:cursor-not-allowed disabled:hover:scale-100"
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
