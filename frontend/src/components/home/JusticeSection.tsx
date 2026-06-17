'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Justice / R4J section — designer-faithful (v3).
 *
 * Backend contract (apps/r4j):
 *   GET /api/v1/r4j/criminals/  → R4JPublicCriminalListSerializer
 * Fields used here:
 *   id, slug, first_name, last_name, country, province, city,
 *   primary_photo{url,…}, total_bounty_toman, bounties_count
 *
 * Layout (matches the latest mockup exactly):
 *   - A single ROW of FOUR criminal cards (the gold trophy CTA is gone).
 *   - More criminals are reached via the bottom pager arrows (same PNG
 *     glyphs that drive the WarFund carousel).
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
 *   │  │  photo  │  │  photo  │  │  photo  │  │  photo  │         │
 *   │  │  [pill] │  │  [pill] │  │  [pill] │  │  [pill] │         │
 *   │  │  name   │  │  name   │  │  name   │  │  name   │         │
 *   │  └─────────┘  └─────────┘  └─────────┘  └─────────┘         │
 *   └──────────────────────────────────────────────────────────────┘
 *                      ◀── ──▶   ← designer pager arrows
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
      strokeWidth={2.3}
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
/*  Card                                                                     */
/* ───────────────────────────────────────────────────────────────────────── */

function CriminalCardView({ p, delay = 0 }: { p: CriminalCard; delay?: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.4, delay }}
      className="group flex flex-col bg-white rounded-2xl overflow-hidden isolate
                 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                 hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.22)]
                 hover:-translate-y-0.5 transition-all duration-300"
    >
      <Link
        href={`/r4j/${p.slug}`}
        className="flex flex-col w-full"
        aria-label={p.fullName}
      >
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

          {/* Action pill — refined orange/red gradient with subtle bevel & shimmer */}
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 w-[88%]">
            <div
              className="relative flex items-center justify-center gap-1.5 h-9 px-3
                         rounded-full text-white text-[12.5px] font-extrabold
                         overflow-hidden
                         shadow-[0_8px_20px_-6px_rgba(229,82,20,.55),inset_0_1px_0_rgba(255,255,255,.35),inset_0_-1px_0_rgba(0,0,0,.10)]
                         ring-1 ring-black/5
                         transition-transform duration-200 group-hover:scale-[1.02]"
              style={{
                backgroundImage:
                  'linear-gradient(180deg, #FF7B2E 0%, #FF6B1A 50%, #E55214 100%)',
              }}
            >
              {/* glossy top highlight */}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-0 top-0 h-1/2 rounded-t-full
                           bg-gradient-to-b from-white/25 to-transparent"
              />
              <GavelIcon className="w-3.5 h-3.5 relative z-10 drop-shadow-[0_1px_0_rgba(0,0,0,.2)]" />
              <span className="relative z-10 drop-shadow-[0_1px_0_rgba(0,0,0,.18)]">
                {p.pillLabel || 'مشارکت در مجازات'}
              </span>
            </div>
          </div>
        </div>

        {/* Green name plate — explicit bottom radii so corners can't bleed */}
        <div
          className="px-3 py-3 bg-brand-500 text-white text-center
                     text-[14px] md:text-[14.5px] font-extrabold leading-6
                     rounded-b-2xl"
        >
          {p.fullName}
        </div>
      </Link>
    </motion.article>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function JusticeSection({ criminals }: { criminals: CriminalCard[] }) {
  // 4 criminals per page — matches the latest designer mockup
  const PAGE_SIZE = 4;
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
          {/* ONE row of FOUR criminal cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-5">
            <AnimatePresence mode="wait" initial={false}>
              {visible.map((p, i) => (
                <CriminalCardView key={`${page}-${p.slug}`} p={p} delay={i * 0.06} />
              ))}
            </AnimatePresence>
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

