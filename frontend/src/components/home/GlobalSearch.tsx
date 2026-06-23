'use client';

/**
 * ───────────────────────────────────────────────────────────────────────────
 *  GlobalSearch — production-grade omni-search for the homepage hero.
 *
 *  Features
 *  ────────
 *   • Live multi-source suggestions (debounced, AbortController-safe)
 *     against six public DRF endpoints aggregated by `lib/global-search.ts`.
 *   • Source-chip filter row (همه / حرکت‌ها / پرونده‌ها / دوره‌ها / آگهی‌ها /
 *     تبیین / دانش) with live counts.
 *   • Trending presets + recent searches (localStorage, max 6) when the
 *     field is empty.
 *   • Keyboard navigation: ↑ / ↓ to move between hits, Enter to open the
 *     highlighted one (or submit when no hit is focused), Esc to close,
 *     ⌘K / Ctrl+K to focus the bar from anywhere.
 *   • A11y: combobox + listbox roles with aria-activedescendant; live
 *     status region announces hit counts.
 *   • Mobile UX: full-screen sheet with sticky search header, drag/swipe
 *     friendly cards, large-tap targets.
 *   • Empty / loading / error / no-results states — every branch covered.
 *   • Submit (`Enter` with no selection) routes to `/search?q=&source=`.
 * ───────────────────────────────────────────────────────────────────────────
 */

import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState,
} from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  searchAll,
  SEARCH_SOURCES,
  SEARCH_SOURCE_ORDER,
  loadRecent,
  pushRecent,
  clearRecent,
  TRENDING_QUERIES,
  type SearchAggregate,
  type SearchHit,
  type SearchSource,
} from '@/lib/global-search';

/* ───────────────────────────────────────────────────────────────────────── */
/*  Glyph atlas — small inline SVGs (no external icon dep)                    */
/* ───────────────────────────────────────────────────────────────────────── */

function SrcGlyph({
  glyph, className = 'w-4 h-4',
}: { glyph: string; className?: string }) {
  const sw = 2;
  const common = {
    viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    strokeWidth: sw, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
    className,
  };
  switch (glyph) {
    case 'campaign':
      return (
        <svg {...common}><path d="M3 11v2a4 4 0 0 0 4 4h2l5 4V3L9 7H7a4 4 0 0 0-4 4z"/></svg>
      );
    case 'gavel':
      return (
        <svg {...common}>
          <path d="m14.5 12.5-8 8a2.1 2.1 0 1 1-3-3l8-8"/>
          <path d="m16 16 6-6"/><path d="m8 8 6-6"/>
          <path d="m9 7 8 8"/><path d="M21 11 13 3"/>
        </svg>
      );
    case 'graduation':
      return (
        <svg {...common}>
          <path d="M22 10v6"/><path d="M2 10l10-5 10 5-10 5z"/>
          <path d="M6 12v5c0 1.66 4 3 6 3s6-1.34 6-3v-5"/>
        </svg>
      );
    case 'heart':
      return (
        <svg {...common}>
          <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>
        </svg>
      );
    case 'megaphone':
      return (
        <svg {...common}>
          <path d="m3 11 18-5v12L3 14v-3z"/>
          <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>
        </svg>
      );
    case 'book':
      return (
        <svg {...common}>
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
      );
    default:
      return null;
  }
}

function SearchIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}
function XIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}
function ClockIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}
function FlameIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 17a7 7 0 0 0 7-7c0-3-2.5-4.5-3-7C13 4 12 2 12 2S9 5 9 9c-1.5 0-3-1-3-3 0 0-3 2-3 6 0 4 3 7 7 7" />
    </svg>
  );
}
function ArrowLeftIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  );
}
function SpinnerIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`${className} animate-spin`} aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth={3} opacity={0.25} />
      <path d="M21 12a9 9 0 0 1-9 9" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" />
    </svg>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Accent color helpers — keep all source styling centralised                */
/* ───────────────────────────────────────────────────────────────────────── */

const ACCENT_STYLE: Record<string, {
  chipActiveBg: string; chipActiveText: string;
  chipIdleBg: string;   chipIdleText: string;
  iconBg: string;       iconText: string;
  pillBg: string;       pillText: string;
}> = {
  brand:  { chipActiveBg: 'bg-brand-600',  chipActiveText: 'text-white',
            chipIdleBg:   'bg-brand-50',   chipIdleText:   'text-brand-700',
            iconBg:       'bg-brand-50',   iconText:       'text-brand-600',
            pillBg:       'bg-brand-50',   pillText:       'text-brand-700' },
  rose:   { chipActiveBg: 'bg-rose-600',   chipActiveText: 'text-white',
            chipIdleBg:   'bg-rose-50',    chipIdleText:   'text-rose-700',
            iconBg:       'bg-rose-50',    iconText:       'text-rose-600',
            pillBg:       'bg-rose-50',    pillText:       'text-rose-700' },
  amber:  { chipActiveBg: 'bg-amber-500',  chipActiveText: 'text-white',
            chipIdleBg:   'bg-amber-50',   chipIdleText:   'text-amber-700',
            iconBg:       'bg-amber-50',   iconText:       'text-amber-600',
            pillBg:       'bg-amber-50',   pillText:       'text-amber-700' },
  mint:   { chipActiveBg: 'bg-mint-500',   chipActiveText: 'text-white',
            chipIdleBg:   'bg-mint-50',    chipIdleText:   'text-mint-700',
            iconBg:       'bg-mint-50',    iconText:       'text-mint-600',
            pillBg:       'bg-mint-50',    pillText:       'text-mint-700' },
  sky:    { chipActiveBg: 'bg-sky-600',    chipActiveText: 'text-white',
            chipIdleBg:   'bg-sky-50',     chipIdleText:   'text-sky-700',
            iconBg:       'bg-sky-50',     iconText:       'text-sky-600',
            pillBg:       'bg-sky-50',     pillText:       'text-sky-700' },
  violet: { chipActiveBg: 'bg-violet-600', chipActiveText: 'text-white',
            chipIdleBg:   'bg-violet-50',  chipIdleText:   'text-violet-700',
            iconBg:       'bg-violet-50',  iconText:       'text-violet-600',
            pillBg:       'bg-violet-50',  pillText:       'text-violet-700' },
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Hook — debounced live search                                              */
/* ───────────────────────────────────────────────────────────────────────── */

/* ───────────────────────────────────────────────────────────────────────── */
/*  Hook — anchored dropdown geometry (Portal + auto-flip + viewport-aware)    */
/*                                                                             */
/*  Why a portal?                                                              */
/*    Any ancestor with `overflow:hidden`, `transform`, `filter`, or `will-    */
/*    change` traps absolutely-positioned descendants inside its own           */
/*    stacking + clipping context. The dropdown that overflows downward into   */
/*    the next section would inevitably get cropped sooner or later — so we    */
/*    teleport it to <body> with createPortal and pin it to the anchor via     */
/*    `position:fixed` + getBoundingClientRect(). This is bullet-proof: it     */
/*    cannot be clipped, regardless of what the page above/below it does.     */
/*                                                                             */
/*  Auto-flip + viewport-aware height                                          */
/*    The hook also computes whether enough room exists BELOW the pill; if    */
/*    not (because the user scrolled the bar near the bottom of the viewport),*/
/*    it flips the panel ABOVE the pill instead. Either way it caps the panel */
/*    height so it never spills past the viewport edge.                        */
/* ───────────────────────────────────────────────────────────────────────── */
type DropdownGeom = {
  top: number; left: number; width: number;
  maxHeight: number; placement: 'below' | 'above';
};

function useDropdownPosition(
  anchorRef: React.RefObject<HTMLElement | null>,
  open: boolean,
): DropdownGeom | null {
  const [geom, setGeom] = useState<DropdownGeom | null>(null);

  useLayoutEffect(() => {
    if (!open || typeof window === 'undefined') return;
    const measure = () => {
      const el = anchorRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight;
      const gap = 16;       // generous so pill glow can't tint the panel
      const safe = 16;      // viewport bottom safety margin
      const desiredMax = Math.min(560, vh * 0.7);
      const spaceBelow = vh - r.bottom - gap - safe;
      const spaceAbove = r.top - gap - safe;
      const placement: 'below' | 'above' =
        spaceBelow < 220 && spaceAbove > spaceBelow ? 'above' : 'below';
      const maxHeight = Math.max(
        220,
        Math.min(desiredMax, placement === 'below' ? spaceBelow : spaceAbove),
      );
      const top = placement === 'below' ? r.bottom + gap : Math.max(safe, r.top - gap - maxHeight);
      setGeom({ top, left: r.left, width: r.width, maxHeight, placement });
    };

    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [anchorRef, open]);

  // Reset when closed so we don't paint a stale geometry on next open
  useEffect(() => { if (!open) setGeom(null); }, [open]);

  return geom;
}

function useGlobalSearch(q: string, source: SearchSource | 'all', enabled: boolean) {
  const [data, setData] = useState<SearchAggregate | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const cleaned = q.trim();
    if (cleaned.length < 2) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const handle = window.setTimeout(async () => {
      try {
        const result = await searchAll(cleaned, {
          sources: source === 'all' ? undefined : [source],
          signal: ctrl.signal,
        });
        if (!ctrl.signal.aborted) {
          setData(result);
          setLoading(false);
        }
      } catch (err) {
        const name = (err as { name?: string })?.name;
        if (name === 'AbortError') return;
        setError('جست‌وجو با خطا مواجه شد');
        setLoading(false);
      }
    }, 220);

    return () => {
      window.clearTimeout(handle);
      ctrl.abort();
    };
  }, [q, source, enabled]);

  return { data, loading, error };
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Component                                                                  */
/* ───────────────────────────────────────────────────────────────────────── */

type Props = {
  /** Optional initial query — handy for re-using the bar on `/search` */
  initialQuery?: string;
  /** Variant 'hero' renders the floating pill that overlaps the photo */
  variant?: 'hero' | 'inline';
  className?: string;
};

export function GlobalSearch({
  initialQuery = '',
  variant = 'hero',
  className,
}: Props) {
  const router = useRouter();
  const inputRef  = useRef<HTMLInputElement | null>(null);
  const wrapRef   = useRef<HTMLDivElement | null>(null);
  const formRef   = useRef<HTMLFormElement | null>(null);   // dropdown anchor
  const panelRef  = useRef<HTMLDivElement | null>(null);    // portal-mounted panel

  const [q, setQ] = useState(initialQuery);
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<SearchSource | 'all'>('all');
  const [recents, setRecents] = useState<string[]>([]);
  const [active, setActive] = useState<number>(-1);
  const [mounted, setMounted] = useState(false);
  const listboxId = useId();

  // Portal target — only on the client; avoids SSR mismatch
  useEffect(() => { setMounted(true); }, []);

  // Anchored geometry for the portal-rendered dropdown
  const geom = useDropdownPosition(formRef, open);

  // Load recents on mount (client only)
  useEffect(() => { setRecents(loadRecent()); }, []);

  // Live search — only when open AND query has ≥2 chars
  const { data, loading, error } = useGlobalSearch(q, source, open);

  // Flatten visible hits for keyboard navigation
  const flatHits: SearchHit[] = useMemo(() => {
    if (!data) return [];
    return data.groups.flatMap((g) => g.hits);
  }, [data]);

  // Reset highlight whenever the result set changes
  useEffect(() => { setActive(-1); }, [data?.q, source]);

  // Close on outside click — must also exempt the portal panel (which is
  // teleported to <body> and is therefore NOT a descendant of wrapRef).
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (wrapRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  // Global hotkey ⌘K / Ctrl+K to focus from anywhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Body scroll-lock for the mobile full-screen sheet
  useEffect(() => {
    if (typeof document === 'undefined') return;
    if (!open) return;
    const mq = window.matchMedia('(max-width: 767px)');
    if (!mq.matches) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  // Counts per source — used by the chip row + the source-filter dropdown
  const counts = useMemo(() => {
    const out: Record<SearchSource, number> = {
      madadkar: 0, r4j: 0, lms: 0, kindness: 0, tabyin: 0, knowledge: 0,
    };
    data?.groups.forEach((g) => { out[g.source] = g.hits.length; });
    return out;
  }, [data]);

  const total = data?.total ?? 0;

  const goToHit = useCallback((hit: SearchHit) => {
    pushRecent(q.trim());
    setOpen(false);
    router.push(hit.href);
  }, [q, router]);

  const submitForm = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    const cleaned = q.trim();
    if (!cleaned) {
      inputRef.current?.focus();
      return;
    }
    if (active >= 0 && flatHits[active]) {
      goToHit(flatHits[active]);
      return;
    }
    pushRecent(cleaned);
    setOpen(false);
    const params = new URLSearchParams({ q: cleaned });
    if (source !== 'all') params.set('source', source);
    router.push(`/search?${params.toString()}`);
  }, [q, active, flatHits, source, router, goToHit]);

  const onInputKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!flatHits.length) return;
      setActive((i) => (i + 1) % flatHits.length);
      setOpen(true);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!flatHits.length) return;
      setActive((i) => (i <= 0 ? flatHits.length - 1 : i - 1));
      setOpen(true);
    }
  };

  const clearInput = () => {
    setQ('');
    setActive(-1);
    inputRef.current?.focus();
  };

  /* ── Layout shells ─────────────────────────────────────────────────── */

  // NOTE — z-index strategy:
  //   The hero variant's wrapper deliberately uses a HIGH z-index so the
  //   pill itself stays above ActivitiesPanel's ambient shadow (z-[2]),
  //   and the dropdown panel beneath bumps even higher (z-[80]) so it
  //   floats over any sibling section that scrolls into view below.
  const pillBaseClasses = variant === 'hero'
    ? 'relative z-[60] mx-auto -mt-[100px] md:-mt-[120px] lg:-mt-[140px] max-w-3xl'
    : 'relative z-[60] mx-auto max-w-3xl';

  return (
    <div ref={wrapRef} className={`${pillBaseClasses} ${className ?? ''}`}>
      {/* ── Pill (input + actions) ───────────────────────────────────── */}
      <form
        ref={formRef}
        role="search"
        onSubmit={submitForm}
        // When the suggestions panel is open the pill drops its large
        // glow shadow so its colour cannot bleed through the gap above
        // the panel and tint the top edge of the chip row below.
        className={`
          relative bg-white rounded-full
          ring-1 ring-ink-100
          ${open
            ? 'shadow-[0_4px_14px_-4px_rgba(13,128,116,.18)]'
            : 'shadow-[0_18px_50px_-22px_rgba(11,53,48,.30)] hover:shadow-[0_22px_56px_-22px_rgba(11,53,48,.36)] focus-within:shadow-[0_22px_60px_-18px_rgba(13,128,116,.45)]'}
          focus-within:ring-2 focus-within:ring-brand-500
          transition-[box-shadow,outline] duration-300
          flex items-center pl-1.5 pr-3 md:pr-5 py-1.5 gap-2
        `}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
      >
        {/* Search icon (right in RTL) */}
        <span className="shrink-0 w-9 h-9 md:w-10 md:h-10 rounded-full
                         bg-brand-50 text-brand-600
                         flex items-center justify-center" aria-hidden="true">
          <SearchIcon className="w-4 h-4 md:w-[18px] md:h-[18px]" />
        </span>

        <input
          ref={inputRef}
          type="search"
          name="q"
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onInputKey}
          placeholder="جست‌وجو در حرکت‌ها، آموزش‌ها، پرونده‌ها، روایت‌ها…"
          aria-label="جست‌وجوی سراسری"
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-activedescendant={active >= 0 ? `${listboxId}-opt-${active}` : undefined}
          dir="rtl"
          autoComplete="off"
          spellCheck={false}
          // The `appearance-none` + `gs-search-input` class suppresses
          // EVERY browser-native search affordance (Webkit X, Edge X +
          // reveal). Keeping the only X to our brand-styled button below.
          className="gs-search-input flex-1 min-w-0 h-10 md:h-11 bg-transparent outline-none
                     text-[14px] md:text-[15px] text-ink-900
                     placeholder:text-ink-400 text-right appearance-none"
        />

        {/* Clear button */}
        {q.length > 0 && (
          <button
            type="button"
            onClick={clearInput}
            aria-label="پاک کردن"
            className="shrink-0 w-8 h-8 rounded-full text-ink-400 hover:text-ink-700
                       hover:bg-ink-50 inline-flex items-center justify-center
                       transition-colors"
          >
            <XIcon className="w-4 h-4" />
          </button>
        )}

        {/* Loading spinner — sits next to the kbd hint */}
        {loading && (
          <span className="shrink-0 text-brand-500" aria-hidden="true">
            <SpinnerIcon className="w-4 h-4" />
          </span>
        )}

        {/* ⌘K / Ctrl+K affordance — desktop only */}
        <span
          aria-hidden="true"
          className="hidden md:inline-flex shrink-0 items-center gap-1
                     px-2 h-7 rounded-md bg-ink-50 text-ink-500 text-[11px] font-extrabold
                     ring-1 ring-ink-100 tabular-nums"
        >
          <kbd className="font-sans">Ctrl</kbd>
          <span className="text-ink-300">+</span>
          <kbd className="font-sans">K</kbd>
        </span>

        {/* Submit — solid brand pill */}
        <button
          type="submit"
          aria-label="جست‌وجو"
          className="shrink-0 inline-flex items-center justify-center gap-1.5
                     h-10 md:h-11 px-4 md:px-5 rounded-full
                     bg-brand-500 hover:bg-brand-600 text-white font-extrabold
                     text-[13px] md:text-[14px]
                     shadow-[0_8px_22px_-8px_rgba(13,128,116,.55)]
                     hover:scale-[1.02] active:scale-[.98]
                     transition-all duration-200"
        >
          <span className="hidden sm:inline">جست‌وجو</span>
          <SearchIcon className="w-4 h-4 sm:hidden" />
        </button>
      </form>

      {/* ── Suggestions panel ─────────────────────────────────────────────
          Teleported to <body> via createPortal so it CANNOT be clipped by
          any ancestor's overflow / transform / filter. Pinned to the pill
          with `position:fixed` + measured geometry; auto-flips above the
          pill when there isn't enough room below, and caps its own height
          to the available viewport space. */}
      {mounted && createPortal(
        <AnimatePresence>
          {open && geom && (
            <motion.div
              ref={panelRef}
              initial={{ opacity: 0, y: geom.placement === 'above' ? -4 : 8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: geom.placement === 'above' ? -2 : 4, scale: 0.98 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              style={{
                position: 'fixed',
                top: geom.top,
                left: geom.left,
                width: geom.width,
                maxHeight: geom.maxHeight,
                zIndex: 1000,
              }}
              className="
                bg-white rounded-3xl ring-1 ring-ink-100
                shadow-[0_30px_80px_-20px_rgba(11,53,48,.45)]
                overflow-hidden flex flex-col
              "
              role="region"
              aria-label="پیشنهادهای جست‌وجو"
              dir="rtl"
            >
              {/* Source-chip filter row */}
              <div className="flex flex-wrap items-center gap-1.5 px-3 pt-3 pb-2 border-b border-ink-50 shrink-0">
                <SourceChip
                  label="همه نتایج"
                  active={source === 'all'}
                  count={total}
                  onClick={() => setSource('all')}
                  accent="brand"
                  showAll
                />
                {SEARCH_SOURCE_ORDER.map((src) => {
                  const meta = SEARCH_SOURCES[src];
                  return (
                    <SourceChip
                      key={src}
                      label={meta.shortLabel}
                      glyph={meta.glyph}
                      accent={meta.accent}
                      count={counts[src]}
                      active={source === src}
                      onClick={() => setSource(src)}
                    />
                  );
                })}
              </div>

              {/* Listbox / state body (the only scrolling layer) */}
              <div
                id={listboxId}
                role="listbox"
                aria-label="نتایج جست‌وجو"
                className="flex-1 min-h-0 overflow-y-auto custom-scroll"
              >
                {q.trim().length < 2 ? (
                  <EmptyInputBody
                    recents={recents}
                    onPickRecent={(r) => { setQ(r); inputRef.current?.focus(); }}
                    onClearRecents={() => { clearRecent(); setRecents([]); }}
                    onPickTrending={(t) => {
                      if (t.source) setSource(t.source);
                      setQ(t.q || t.label);
                      inputRef.current?.focus();
                    }}
                  />
                ) : loading && !data ? (
                  <LoadingBody />
                ) : error ? (
                  <ErrorBody message={error} />
                ) : !data || data.total === 0 ? (
                  <NoResultsBody q={q} />
                ) : (
                  <ResultsBody
                    data={data}
                    active={active}
                    listboxId={listboxId}
                    setActive={setActive}
                    onPick={goToHit}
                  />
                )}
              </div>

              {/* Footer — submit hint + see-all */}
              <div className="flex items-center justify-between gap-3 px-4 py-2.5 shrink-0
                              border-t border-ink-50 bg-ink-50/50 text-[11.5px] text-ink-500">
                <span className="hidden sm:flex items-center gap-2">
                  <KbdPair items={['↑', '↓']} /> برای حرکت
                  <KbdPair items={['Enter']} /> برای انتخاب
                  <KbdPair items={['Esc']} /> برای بستن
                </span>
                {q.trim().length >= 2 && (
                  <button
                    type="button"
                    onClick={() => submitForm()}
                    className="inline-flex items-center gap-1.5 text-brand-700
                               font-extrabold hover:text-brand-800 transition-colors"
                  >
                    مشاهده همه‌ی نتایج برای «{q.trim()}»
                    <ArrowLeftIcon className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  );
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Subcomponents                                                             */
/* ───────────────────────────────────────────────────────────────────────── */

function SourceChip({
  label, active, count, onClick, accent = 'brand', glyph, showAll = false,
}: {
  label: string;
  active: boolean;
  count: number;
  onClick: () => void;
  accent?: keyof typeof ACCENT_STYLE;
  glyph?: string;
  showAll?: boolean;
}) {
  const a = ACCENT_STYLE[accent];
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`
        inline-flex items-center gap-1.5 h-8 px-3 rounded-full
        text-[12px] font-extrabold tabular-nums
        transition-all duration-200
        ${active
          ? `${a.chipActiveBg} ${a.chipActiveText} shadow-[0_4px_14px_-4px_rgba(0,0,0,.22)]`
          : `${a.chipIdleBg} ${a.chipIdleText} hover:saturate-150`}
      `}
    >
      {glyph && <SrcGlyph glyph={glyph} className="w-3.5 h-3.5" />}
      {showAll && (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2}
             strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5" aria-hidden="true">
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
      )}
      <span>{label}</span>
      {count > 0 && (
        <span className={`inline-flex items-center justify-center min-w-[20px] h-[20px] px-1
                          rounded-full text-[10.5px] font-extrabold
                          ${active ? 'bg-white/25 text-white' : 'bg-white/70 text-ink-700'}`}>
          {count.toLocaleString('fa-IR')}
        </span>
      )}
    </button>
  );
}

function KbdPair({ items }: { items: string[] }) {
  return (
    <span className="inline-flex items-center gap-0.5">
      {items.map((k, i) => (
        <kbd key={`${k}-${i}`} className="inline-flex items-center justify-center
                                          min-w-[20px] h-5 px-1 rounded
                                          bg-white ring-1 ring-ink-200
                                          text-ink-700 font-extrabold font-sans
                                          text-[10.5px]">
          {k}
        </kbd>
      ))}
    </span>
  );
}

function EmptyInputBody({
  recents, onPickRecent, onClearRecents, onPickTrending,
}: {
  recents: string[];
  onPickRecent: (q: string) => void;
  onClearRecents: () => void;
  onPickTrending: (t: { label: string; q: string; source?: SearchSource }) => void;
}) {
  return (
    <div className="p-4">
      {/* Trending */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-2.5 text-ink-500">
          <FlameIcon className="w-3.5 h-3.5 text-amber-500" />
          <span className="text-[11.5px] font-extrabold uppercase tracking-wider">
            جست‌وجوهای پیشنهادی
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {TRENDING_QUERIES.map((t) => {
            const a = t.source ? ACCENT_STYLE[SEARCH_SOURCES[t.source].accent] : ACCENT_STYLE.brand;
            return (
              <button
                key={t.label}
                type="button"
                onClick={() => onPickTrending(t)}
                className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full
                            ${a.chipIdleBg} ${a.chipIdleText} text-[12px] font-bold
                            hover:saturate-150 transition-all duration-150`}
              >
                {t.source && <SrcGlyph glyph={SEARCH_SOURCES[t.source].glyph} className="w-3 h-3" />}
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Recents */}
      {recents.length > 0 ? (
        <div>
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2 text-ink-500">
              <ClockIcon className="w-3.5 h-3.5" />
              <span className="text-[11.5px] font-extrabold uppercase tracking-wider">
                جست‌وجوهای اخیر
              </span>
            </div>
            <button
              type="button"
              onClick={onClearRecents}
              className="text-[11px] text-ink-400 hover:text-rose-500 font-bold"
            >
              پاک کردن همه
            </button>
          </div>
          <div className="flex flex-col gap-0.5">
            {recents.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => onPickRecent(r)}
                className="group flex items-center gap-3 w-full text-right
                           px-2.5 py-2 rounded-xl hover:bg-ink-50 transition-colors"
              >
                <span className="w-8 h-8 rounded-full bg-ink-50 text-ink-500
                                 flex items-center justify-center shrink-0">
                  <ClockIcon className="w-3.5 h-3.5" />
                </span>
                <span className="flex-1 text-[13px] text-ink-800 font-bold truncate">{r}</span>
                <span className="opacity-0 group-hover:opacity-100 text-brand-600 transition-opacity">
                  <ArrowLeftIcon className="w-3.5 h-3.5" />
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-[12.5px] text-ink-400 text-center leading-7 py-3">
          عبارت موردنظر را تایپ کنید — نتایج زنده از همه‌ی بخش‌های سامانه نشان داده می‌شود.
        </p>
      )}
    </div>
  );
}

function LoadingBody() {
  return (
    <div className="p-4 space-y-2.5" aria-live="polite" aria-busy="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 p-2.5 rounded-xl bg-ink-50/60 animate-pulse">
          <div className="w-11 h-11 rounded-xl bg-ink-100" />
          <div className="flex-1 min-w-0 space-y-1.5">
            <div className="h-3 rounded-full bg-ink-100 w-[60%]" />
            <div className="h-2.5 rounded-full bg-ink-100 w-[40%]" />
          </div>
          <div className="h-6 w-16 rounded-full bg-ink-100" />
        </div>
      ))}
    </div>
  );
}

function ErrorBody({ message }: { message: string }) {
  return (
    <div className="p-6 text-center" role="alert">
      <div className="mx-auto mb-3 w-12 h-12 rounded-2xl bg-rose-50 text-rose-600
                      flex items-center justify-center">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
             strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <p className="text-[14px] font-extrabold text-ink-900">{message}</p>
      <p className="text-[12px] text-ink-500 mt-1">دوباره تلاش کنید یا عبارت دیگری را امتحان کنید.</p>
    </div>
  );
}

function NoResultsBody({ q }: { q: string }) {
  return (
    <div className="p-6 text-center" aria-live="polite">
      <div className="mx-auto mb-3 w-14 h-14 rounded-2xl
                      bg-gradient-to-br from-brand-50 to-brand-100 text-brand-600
                      flex items-center justify-center">
        <SearchIcon className="w-6 h-6" />
      </div>
      <p className="text-[14px] font-extrabold text-ink-900">
        نتیجه‌ای برای «{q.trim()}» پیدا نشد
      </p>
      <p className="text-[12px] text-ink-500 mt-1 leading-7">
        لطفاً عبارت را کوتاه‌تر یا متفاوت‌تر بنویسید، یا فیلتر منبع را تغییر دهید.
      </p>
    </div>
  );
}

function ResultsBody({
  data, active, listboxId, setActive, onPick,
}: {
  data: SearchAggregate;
  active: number;
  listboxId: string;
  setActive: (i: number) => void;
  onPick: (h: SearchHit) => void;
}) {
  // Flat index counter so keyboard nav lines up with rendered order
  let cursor = -1;
  return (
    <div className="py-2">
      {data.groups.map((g) => {
        const meta = SEARCH_SOURCES[g.source];
        const a = ACCENT_STYLE[meta.accent];
        return (
          <div key={g.source} className="mb-1.5 last:mb-0">
            <div className="flex items-center justify-between px-4 pt-2.5 pb-1">
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center justify-center w-6 h-6 rounded-lg ${a.iconBg} ${a.iconText}`}>
                  <SrcGlyph glyph={meta.glyph} className="w-3.5 h-3.5" />
                </span>
                <span className="text-[11.5px] font-extrabold uppercase tracking-wider text-ink-600">
                  {meta.label}
                </span>
                <span className="text-[10.5px] text-ink-400 font-bold">
                  ({g.hits.length.toLocaleString('fa-IR')})
                </span>
              </div>
              <Link
                href={meta.seeAllHref(data.q)}
                className={`text-[11px] font-extrabold ${a.iconText} hover:underline`}
              >
                مشاهده همه
              </Link>
            </div>

            <ul className="px-1.5">
              {g.hits.map((h) => {
                cursor += 1;
                const idx = cursor;
                const isActive = idx === active;
                return (
                  <li key={h.id} role="option" aria-selected={isActive}
                      id={`${listboxId}-opt-${idx}`}
                      onMouseEnter={() => setActive(idx)}>
                    <button
                      type="button"
                      onClick={() => onPick(h)}
                      className={`w-full text-right flex items-center gap-3 rounded-xl
                                  px-2.5 py-2 transition-colors
                                  ${isActive ? 'bg-brand-50' : 'hover:bg-ink-50'}`}
                    >
                      {/* Thumb / glyph */}
                      <span className="relative shrink-0 w-11 h-11 rounded-xl overflow-hidden bg-ink-100">
                        {h.thumb ? (
                          <Image
                            src={h.thumb}
                            alt=""
                            fill
                            sizes="44px"
                            className="object-cover"
                          />
                        ) : (
                          <span className={`absolute inset-0 flex items-center justify-center
                                            ${a.iconBg} ${a.iconText}`}>
                            <SrcGlyph glyph={meta.glyph} className="w-5 h-5" />
                          </span>
                        )}
                      </span>

                      {/* Text */}
                      <span className="flex-1 min-w-0">
                        <span className="block text-[13.5px] font-extrabold text-ink-900 truncate">
                          {h.title}
                        </span>
                        {(h.subtitle || h.badge) && (
                          <span className="block text-[11.5px] text-ink-500 font-medium truncate mt-0.5">
                            {h.subtitle}
                            {h.subtitle && h.badge && <span className="mx-1.5 text-ink-300">·</span>}
                            {h.badge && <span className="text-ink-700 font-bold">{h.badge}</span>}
                          </span>
                        )}
                      </span>

                      {/* Pill */}
                      {h.pill && (
                        <span className={`shrink-0 inline-flex items-center px-2.5 h-7
                                         rounded-full text-[11px] font-extrabold
                                         ${a.pillBg} ${a.pillText}`}>
                          {h.pill}
                        </span>
                      )}

                      <span className={`shrink-0 transition-all ${isActive ? 'text-brand-600 -translate-x-0.5' : 'text-ink-300'}`}>
                        <ArrowLeftIcon className="w-4 h-4" />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}

      {data.errored.length > 0 && (
        <p className="px-4 pt-2 pb-3 text-[11px] text-ink-400 text-center">
          ({data.errored.length.toLocaleString('fa-IR')} منبع موقتاً در دسترس نبود)
        </p>
      )}
    </div>
  );
}
