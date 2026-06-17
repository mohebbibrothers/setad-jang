'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState, useMemo, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SectionTitle } from './SectionTitle';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * Justice / R4J section — designer-faithful (v4).
 *
 * Backend contract (apps/r4j):
 *   GET /api/v1/r4j/criminals/  → R4JPublicCriminalListSerializer
 *
 * Layout:
 *   - One row of FOUR criminal cards (no trophy CTA — moved to /r4j page)
 *   - Bottom pager arrows cycle additional pages of criminals
 *
 * Action button (UX-driven, applied colour-psychology + modern UI):
 *   - The orange pill is now a SPLIT-ACTION control. Hover / click /
 *     focus opens a tasteful glassy popover ABOVE the pill carrying two
 *     primary actions that come straight from the R4J product brief:
 *
 *        ┌──────────────────────────────┐
 *        │  🏆  ثبت جایزه          ←   │   accent-orange highlight
 *        ├──────────────────────────────┤   (action-leaning option)
 *        │  📋  گزارش اطلاعات      ←   │   brand-teal highlight
 *        └─────────────▼────────────────┘   (information-leaning option)
 *
 *        ┌──────────────────────────────┐
 *        │  ⚖  مشارکت در مجازات   ⌄   │   ← glossy pill, chev rotates
 *        └──────────────────────────────┘
 *
 *   Colour psychology:
 *     - Orange/red gradient on the trigger → urgency, justice, action.
 *     - 'ثبت جایزه' (commit) → accent-orange tint, matches the trigger.
 *     - 'گزارش اطلاعات' (inform) → brand-teal tint, signals reporting /
 *       trustworthy information path.
 *     - White card with hairline ring + heavy ambient shadow → premium
 *       'lifted glass' feel without competing with the photo.
 * ───────────────────────────────────────────────────────────────────────────
 */
export type CriminalCard = {
  slug: string;
  fullName: string;
  pillLabel?: string;
  imageUrl?: string;
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Icons                                                                    */
/* ───────────────────────────────────────────────────────────────────────── */

function GavelIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.3}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m14.5 12.5-8 8a2.119 2.119 0 1 1-3-3l8-8" />
      <path d="m16 16 6-6" /><path d="m8 8 6-6" />
      <path d="m9 7 8 8" /><path d="m21 11-8-8" />
    </svg>
  );
}
function ChevronDownIcon({ className = 'w-3 h-3' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}
function ChevronLeftIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}
function TrophyIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
      <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
      <path d="M4 22h16" />
      <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
      <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
      <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
    </svg>
  );
}
function InfoIcon({ className = 'w-3.5 h-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="9" y1="13" x2="15" y2="13" />
      <line x1="9" y1="17" x2="13" y2="17" />
    </svg>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Split-action pill with popover menu                                      */
/* ───────────────────────────────────────────────────────────────────────── */

function ActionPill({ slug, label = 'مشارکت در مجازات' }: { slug: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Click outside closes (touch / desktop alike)
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent | TouchEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('touchstart', onDown, { passive: true });
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
    };
  }, [open]);

  // Hover-delay-close so the cursor can slip from pill → menu
  const enter = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const leave = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 180);
  };

  return (
    <div
      ref={wrapRef}
      onMouseEnter={enter}
      onMouseLeave={leave}
      className="absolute bottom-3.5 left-1/2 -translate-x-1/2 w-[88%] z-20"
    >
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 380, damping: 26, mass: 0.6 }}
            className="absolute inset-x-0 bottom-[calc(100%+10px)]
                       bg-white rounded-2xl overflow-hidden
                       shadow-[0_24px_60px_-12px_rgba(0,0,0,.35),0_0_0_1px_rgba(217,222,229,.7)]
                       backdrop-blur-xl"
            role="menu"
            aria-label={`${label} — گزینه‌ها`}
          >
            {/* Option 1: ثبت جایزه — accent (urgent, action-leaning) */}
            <Link
              href={`/r4j/${slug}/bounty`}
              role="menuitem"
              className="group/item relative flex items-center gap-2.5 px-3.5 h-12
                         hover:bg-accent-500/[0.07] transition-colors duration-150"
            >
              <span
                className="flex items-center justify-center w-8 h-8 rounded-xl shrink-0
                           bg-accent-500/[0.12] text-accent-600
                           group-hover/item:bg-accent-500 group-hover/item:text-white
                           group-hover/item:shadow-[0_6px_16px_-4px_rgba(229,82,20,.5)]
                           transition-all duration-200"
              >
                <TrophyIcon className="w-3.5 h-3.5" />
              </span>
              <span className="flex-1 text-right text-[12.5px] font-extrabold text-ink-800
                               group-hover/item:text-accent-700 transition-colors">
                ثبت جایزه
              </span>
              <ChevronLeftIcon className="w-3.5 h-3.5 text-ink-400
                                          group-hover/item:text-accent-600
                                          group-hover/item:-translate-x-0.5
                                          transition-all duration-200" />
            </Link>

            <div className="mx-2 h-px bg-gradient-to-l from-transparent via-ink-100 to-transparent" />

            {/* Option 2: گزارش اطلاعات — brand-teal (informational, trustworthy) */}
            <Link
              href={`/r4j/${slug}/report`}
              role="menuitem"
              className="group/item relative flex items-center gap-2.5 px-3.5 h-12
                         hover:bg-brand-500/[0.07] transition-colors duration-150"
            >
              <span
                className="flex items-center justify-center w-8 h-8 rounded-xl shrink-0
                           bg-brand-500/[0.12] text-brand-600
                           group-hover/item:bg-brand-500 group-hover/item:text-white
                           group-hover/item:shadow-[0_6px_16px_-4px_rgba(13,128,116,.5)]
                           transition-all duration-200"
              >
                <InfoIcon className="w-3.5 h-3.5" />
              </span>
              <span className="flex-1 text-right text-[12.5px] font-extrabold text-ink-800
                               group-hover/item:text-brand-700 transition-colors">
                گزارش اطلاعات
              </span>
              <ChevronLeftIcon className="w-3.5 h-3.5 text-ink-400
                                          group-hover/item:text-brand-600
                                          group-hover/item:-translate-x-0.5
                                          transition-all duration-200" />
            </Link>

            {/* Tail — small white diamond pointing down to the pill */}
            <div
              aria-hidden="true"
              className="absolute left-1/2 -translate-x-1/2 -bottom-1.5 w-3 h-3 rotate-45 bg-white"
              style={{ boxShadow: '1px 1px 0 rgba(217,222,229,.7)' }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Trigger: glossy gradient pill with chevron */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`relative w-full flex items-center justify-center gap-1.5 h-10 px-3.5
                    rounded-full text-white text-[12.5px] font-extrabold overflow-hidden
                    ring-1 ring-black/5 transition-all duration-200
                    ${open ? 'scale-[1.03] -translate-y-0.5' : 'hover:scale-[1.02]'}`}
        style={{
          backgroundImage: 'linear-gradient(180deg, #FF7B2E 0%, #FF6B1A 50%, #E55214 100%)',
          boxShadow: open
            ? '0 14px 32px -8px rgba(229,82,20,.65), inset 0 1px 0 rgba(255,255,255,.4), inset 0 -1px 0 rgba(0,0,0,.12)'
            : '0 8px 20px -6px rgba(229,82,20,.55), inset 0 1px 0 rgba(255,255,255,.35), inset 0 -1px 0 rgba(0,0,0,.1)',
        }}
      >
        {/* Top gloss */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-1/2 rounded-t-full
                     bg-gradient-to-b from-white/25 to-transparent"
        />
        <GavelIcon className="w-3.5 h-3.5 relative z-10 drop-shadow-[0_1px_0_rgba(0,0,0,.2)]" />
        <span className="relative z-10 drop-shadow-[0_1px_0_rgba(0,0,0,.18)]">{label}</span>
        <ChevronDownIcon
          className={`w-3 h-3 relative z-10 transition-transform duration-300
                      ${open ? 'rotate-180' : ''}`}
        />
      </button>
    </div>
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
      className="group flex flex-col bg-white rounded-[28px] overflow-hidden isolate
                 shadow-[0_2px_10px_-4px_rgba(15,20,32,.06)]
                 hover:shadow-[0_22px_44px_-22px_rgba(11,53,48,.22)]
                 hover:-translate-y-0.5 transition-all duration-300"
    >
      {/* Photo — relative + overflow-hidden so the popover can pop INTO
          the upper part of the portrait without ever leaving the card. */}
      <div className="relative aspect-[3/4] bg-ink-200 overflow-hidden">
        <Link
          href={`/r4j/${p.slug}`}
          aria-label={p.fullName}
          className="absolute inset-0 block"
        >
          {p.imageUrl ? (
            <Image
              src={p.imageUrl}
              alt={p.fullName}
              fill
              sizes="(max-width: 768px) 50vw, 25vw"
              className="object-cover transition-transform duration-500 group-hover:scale-105"
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-ink-300 to-ink-500
                            flex items-center justify-center text-white/40 text-6xl font-extrabold">
              ?
            </div>
          )}
        </Link>

        {/* Split-action pill — popover opens upward inside the photo */}
        <ActionPill slug={p.slug} />
      </div>

      {/* Green name plate */}
      <Link
        href={`/r4j/${p.slug}`}
        className="block px-3 pt-3 pb-3 bg-brand-500 text-white text-center
                   text-[14px] md:text-[14.5px] font-extrabold leading-6
                   rounded-b-[28px] hover:bg-brand-600 transition-colors"
      >
        {p.fullName}
      </Link>
    </motion.article>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Section                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

export function JusticeSection({ criminals }: { criminals: CriminalCard[] }) {
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

        {/* Off-white panel — corners follow the Apple HIG concentric-corners
            rule: outer_radius ≈ inner_card_radius (28px) + panel_padding.
            So panel goes 32 → 48 → 56px as the inner padding grows.        */}
        <div className="bg-ink-50/60
                        rounded-[32px] md:rounded-[48px] lg:rounded-[56px]
                        p-4 md:p-8 lg:p-10 border border-ink-100">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-5">
            <AnimatePresence mode="wait" initial={false}>
              {visible.map((p, i) => (
                <CriminalCardView key={`${page}-${p.slug}`} p={p} delay={i * 0.06} />
              ))}
            </AnimatePresence>
          </div>
        </div>

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
            <Image src="/brand/pager-arrow-prev.png" alt="" fill sizes="48px" className="object-contain" />
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
            <Image src="/brand/pager-arrow-next.png" alt="" fill sizes="48px" className="object-contain" />
          </button>
        </div>
      </div>
    </section>
  );
}
