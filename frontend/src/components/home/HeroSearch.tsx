'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  useCallback, useEffect, useMemo, useRef, useState,
} from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Icon, type IconName } from '@/components/icons/Icon';
import {
  globalSearch,
  type SearchResults,
  type SearchScope,
  type SearchHit,
  type SearchScopeResult,
  SCOPE_META,
  SCOPE_ORDER,
  getRecentSearches,
  pushRecentSearch,
  clearRecentSearches,
  TRENDING_QUERIES,
} from '@/lib/global-search';

/**
 * HeroSearch — production-grade global search affordance on the homepage.
 *
 * What it does
 *  - Single input that fans-out to every public list endpoint in parallel
 *    (madadkar campaigns + r4j criminals + lms courses + kindness listings
 *    + tabyin contents).
 *  - Scope chips below the bar let users narrow to one domain. The chips
 *    map 1:1 to the `?search=` query string each backend filter accepts.
 *  - Debounced live results dropdown grouped by scope, with rich rows
 *    (thumb, title, contextual subtitle, money / level / location badge).
 *  - Recent searches (localStorage) + curated trending chips when empty.
 *  - Full keyboard support: ↑/↓ to navigate hits, Enter to open, Esc to
 *    close, '/' to focus from anywhere on the page.
 *  - Click-outside dismissal, body-aware aria status messages, abort
 *    controller cancels in-flight queries when the user keeps typing.
 *  - "همه نتایج" footer link routes to /search?q=...&scope=... so the
 *    full search page (Phase 2) keeps state on hand-off.
 */

/* ─── Persian number formatter ─────────────────────────────────────────── */
const fa = (n: number | string) => Number(n).toLocaleString('fa-IR');

/* ─── Icon helpers ─────────────────────────────────────────────────────── */
const SCOPE_ICON: Record<keyof typeof SCOPE_META, IconName> = {
  campaign: 'heart-handshake',
  criminal: 'gavel',
  course:   'graduation',
  listing:  'gift',
  tabyin:   'sparkles',
};

/* ─── Tiny highlight helper — wraps matches in <mark> ──────────────────── */
function Highlight({ text, term }: { text: string; term: string }) {
  const t = (term ?? '').trim();
  if (!t || t.length < 2) return <>{text}</>;
  const re = new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  const parts = text.split(re);
  return (
    <>
      {parts.map((p, i) =>
        re.test(p)
          ? <mark key={i} className="bg-mint-100 text-brand-900 px-0.5 rounded">{p}</mark>
          : <span key={i}>{p}</span>,
      )}
    </>
  );
}

/* ─── Public component ─────────────────────────────────────────────────── */
export function HeroSearch() {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [q, setQ] = useState('');
  const [scope, setScope] = useState<SearchScope>('all');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const [activeIndex, setActiveIndex] = useState<number>(-1);

  /* Flat hit list — needed for keyboard navigation across groups. */
  const flatHits: SearchHit[] = useMemo(() => {
    if (!results) return [];
    return results.scopes.flatMap((s) => s.hits);
  }, [results]);

  /* Hydrate recent searches on mount. */
  useEffect(() => { setRecent(getRecentSearches()); }, []);

  /* Debounced live search. */
  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setResults(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    const ctrl = new AbortController();
    abortRef.current?.abort();
    abortRef.current = ctrl;

    const t = window.setTimeout(async () => {
      try {
        const r = await globalSearch(term, scope, ctrl.signal);
        if (!ctrl.signal.aborted) {
          setResults(r);
          setActiveIndex(-1);
        }
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    }, 240);
    return () => { window.clearTimeout(t); ctrl.abort(); };
  }, [q, scope]);

  /* Global '/' shortcut focuses the bar (skip when typing in another field). */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || (e.target as HTMLElement)?.isContentEditable) return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  /* Click-outside dismissal. */
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!open) return;
      const inForm = formRef.current?.contains(e.target as Node);
      const inDrop = dropdownRef.current?.contains(e.target as Node);
      if (!inForm && !inDrop) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const commitQuery = useCallback((term: string) => {
    const t = term.trim();
    if (!t) return;
    const next = pushRecentSearch(t);
    setRecent(next);
    setOpen(false);
    const scopeParam = scope !== 'all' ? `&scope=${scope}` : '';
    router.push(`/search?q=${encodeURIComponent(t)}${scopeParam}`);
  }, [router, scope]);

  const openHit = useCallback((hit: SearchHit) => {
    const next = pushRecentSearch(q.trim());
    setRecent(next);
    setOpen(false);
    router.push(hit.href);
  }, [q, router]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (activeIndex >= 0 && flatHits[activeIndex]) {
      openHit(flatHits[activeIndex]);
    } else {
      commitQuery(q);
    }
  };

  const onInputKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur(); return; }
    if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) setOpen(true);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, flatHits.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, -1));
    }
  };

  const showEmpty = !q.trim();
  const showResults = !showEmpty && (loading || results !== null);
  const hasAnyHits = !!results && results.total > 0;

  return (
    <div className="relative z-30 mx-auto -mt-[100px] md:-mt-[120px] lg:-mt-[140px] max-w-3xl">
      {/* ─── Search pill ─── */}
      <motion.form
        ref={formRef}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
        role="search"
        action="/search"
        method="get"
        onSubmit={onSubmit}
        className={`relative bg-white rounded-full
                    flex items-center pl-1.5 pr-6 py-1.5 gap-2
                    ring-1 ring-ink-100/60
                    shadow-[0_10px_30px_-18px_rgba(11,53,48,0.18)]
                    focus-within:ring-2 focus-within:ring-brand-300
                    focus-within:shadow-[0_18px_38px_-18px_rgba(11,53,48,0.28)]
                    transition-all duration-200`}
      >
        {/* hidden inputs so non-JS submit still routes to /search */}
        {scope !== 'all' && <input type="hidden" name="scope" value={scope} />}

        <Icon name="search" className="w-5 h-5 text-brand-500 shrink-0 mr-1" />

        <input
          ref={inputRef}
          type="search"
          name="q"
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onInputKey}
          placeholder="جست‌وجو در حرکت‌ها، دوره‌ها، پرونده‌ها، آگهی‌ها و محتواها…"
          aria-label="جست‌وجو در سایت"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls="hero-search-listbox"
          autoComplete="off"
          spellCheck={false}
          dir="rtl"
          className="flex-1 h-10 md:h-11 bg-transparent outline-none text-[14px] md:text-[15px]
                     text-ink-900 placeholder:text-ink-400 text-right"
        />

        {/* Right side: clear button + ⌘K hint + submit */}
        {q && (
          <button
            type="button"
            onClick={() => { setQ(''); inputRef.current?.focus(); }}
            aria-label="پاک‌کردن"
            className="w-8 h-8 rounded-full text-ink-400 hover:bg-ink-50 hover:text-ink-700
                       inline-flex items-center justify-center transition-colors shrink-0"
          >
            <Icon name="close" className="w-4 h-4" strokeWidth={2.4} />
          </button>
        )}

        <kbd className="hidden md:inline-flex items-center justify-center h-7 px-2 rounded-md
                        text-[11px] font-extrabold text-ink-500 bg-ink-50 ring-1 ring-ink-100
                        select-none">
          /
        </kbd>

        <button
          type="submit"
          aria-label="جست‌وجو"
          className="w-10 h-10 md:w-11 md:h-11 rounded-full bg-brand-500 text-white
                     hover:bg-brand-600 active:scale-95
                     inline-flex items-center justify-center transition-all shrink-0
                     shadow-[0_8px_22px_-8px_rgba(13,128,116,.55)]"
        >
          <Icon name="search" className="w-5 h-5" strokeWidth={2.4} />
        </button>
      </motion.form>

      {/* ─── Scope chip strip ─── */}
      <div className="mt-3 px-2 flex flex-wrap items-center justify-center gap-1.5">
        <ScopeChip
          active={scope === 'all'}
          onClick={() => setScope('all')}
          label="همه"
          icon="grid"
        />
        {SCOPE_ORDER.map((s) => (
          <ScopeChip
            key={s}
            active={scope === s}
            onClick={() => setScope(s)}
            label={SCOPE_META[s].short}
            icon={SCOPE_ICON[s]}
            tone={SCOPE_META[s].tone}
          />
        ))}
      </div>

      {/* ─── Dropdown ─── */}
      <AnimatePresence>
        {open && (
          <motion.div
            ref={dropdownRef}
            id="hero-search-listbox"
            role="listbox"
            initial={{ opacity: 0, y: -8, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.99 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="absolute top-full inset-x-0 mt-3 origin-top
                       rounded-3xl bg-white ring-1 ring-ink-100/80
                       shadow-[0_28px_60px_-22px_rgba(11,53,48,0.32)]
                       max-h-[78vh] overflow-y-auto overscroll-contain
                       backdrop-blur-sm"
            style={{ direction: 'rtl' }}
          >
            {showEmpty ? (
              <EmptyHelpers
                recent={recent}
                onPick={(term) => { setQ(term); inputRef.current?.focus(); }}
                onClearRecent={() => { clearRecentSearches(); setRecent([]); }}
              />
            ) : loading && !results ? (
              <LoadingPanel />
            ) : !hasAnyHits ? (
              <NoResults q={q} onTryAll={() => setScope('all')} />
            ) : (
              <ResultsPanel
                results={results!}
                query={q}
                flatHits={flatHits}
                activeIndex={activeIndex}
                setActiveIndex={setActiveIndex}
                onPick={openHit}
                onSeeAll={() => commitQuery(q)}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Scope chip                                                              */
/* ─────────────────────────────────────────────────────────────────────── */

function ScopeChip({
  active, onClick, label, icon, tone = 'all',
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon: IconName;
  tone?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-tone={tone}
      className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full
                  text-[12px] font-extrabold transition-all duration-200
                  ring-1 ${active
                    ? 'bg-white text-brand-700 ring-brand-300 shadow-[0_4px_12px_-4px_rgba(13,128,116,.45)] scale-[1.02]'
                    : 'bg-white/85 text-ink-600 ring-white/60 hover:bg-white hover:text-brand-700'}
                  backdrop-blur-sm`}
    >
      <Icon name={icon} className="w-3.5 h-3.5" />
      {label}
    </button>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Empty-state helpers (recent + trending)                                 */
/* ─────────────────────────────────────────────────────────────────────── */

function EmptyHelpers({
  recent, onPick, onClearRecent,
}: {
  recent: string[];
  onPick: (q: string) => void;
  onClearRecent: () => void;
}) {
  return (
    <div className="p-5 md:p-6">
      {recent.length > 0 && (
        <section className="mb-5">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-[12px] font-extrabold text-ink-500 inline-flex items-center gap-1.5">
              <Icon name="clock" className="w-3.5 h-3.5" /> جست‌وجوهای اخیر
            </h4>
            <button
              type="button"
              onClick={onClearRecent}
              className="text-[11px] text-ink-400 hover:text-rose-500 font-bold transition-colors"
            >
              پاک‌کردن
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {recent.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => onPick(r)}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full
                           bg-ink-50 hover:bg-brand-50 hover:text-brand-700
                           text-ink-700 text-[12px] font-bold transition-colors
                           ring-1 ring-ink-100"
              >
                <Icon name="clock" className="w-3 h-3 text-ink-400" />
                {r}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="mb-5">
        <h4 className="text-[12px] font-extrabold text-ink-500 mb-2 inline-flex items-center gap-1.5">
          <Icon name="sparkles" className="w-3.5 h-3.5 text-accent-500" /> پیشنهادهای داغ
        </h4>
        <div className="flex flex-wrap gap-1.5">
          {TRENDING_QUERIES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => onPick(t)}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full
                         bg-gradient-to-br from-brand-50 to-mint-50
                         hover:from-brand-100 hover:to-mint-100
                         text-brand-700 text-[12px] font-extrabold transition-colors
                         ring-1 ring-brand-100"
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      <section>
        <h4 className="text-[12px] font-extrabold text-ink-500 mb-2 inline-flex items-center gap-1.5">
          <Icon name="grid" className="w-3.5 h-3.5" /> دسته‌بندی‌ها
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {SCOPE_ORDER.map((s) => (
            <Link
              key={s}
              href={SCOPE_META[s].href}
              className="group flex flex-col items-center justify-center gap-1.5 py-3.5
                         rounded-2xl bg-white hover:bg-brand-50/60
                         ring-1 ring-ink-100 hover:ring-brand-200
                         transition-all text-center"
            >
              <span className="w-10 h-10 rounded-xl bg-brand-50 text-brand-600
                               flex items-center justify-center
                               group-hover:bg-brand-500 group-hover:text-white
                               transition-colors">
                <Icon name={SCOPE_ICON[s]} className="w-5 h-5" />
              </span>
              <span className="text-[11.5px] font-extrabold text-ink-700">
                {SCOPE_META[s].short}
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Loading + no-results                                                    */
/* ─────────────────────────────────────────────────────────────────────── */

function LoadingPanel() {
  return (
    <div className="p-5 md:p-6 space-y-3" aria-live="polite">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 animate-pulse">
          <div className="w-12 h-12 rounded-xl bg-ink-100 shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-2/3 rounded bg-ink-100" />
            <div className="h-2.5 w-1/3 rounded bg-ink-100" />
          </div>
        </div>
      ))}
    </div>
  );
}

function NoResults({ q, onTryAll }: { q: string; onTryAll: () => void }) {
  return (
    <div className="px-5 py-10 md:py-12 text-center">
      <div className="mx-auto mb-4 w-14 h-14 rounded-2xl
                      bg-gradient-to-br from-brand-50 to-brand-100
                      text-brand-600 flex items-center justify-center
                      ring-1 ring-brand-100">
        <Icon name="search" className="w-6 h-6" />
      </div>
      <h3 className="text-[15px] font-extrabold text-ink-900">
        برای «<span className="text-brand-600">{q}</span>» چیزی پیدا نشد
      </h3>
      <p className="mt-2 text-[12.5px] text-ink-500 font-medium leading-7 max-w-sm mx-auto">
        املای کلیدواژه را بررسی کن، عبارت کوتاه‌تری امتحان کن، یا روی «همه» بزن تا در همه‌ی بخش‌ها بگردیم.
      </p>
      <button
        type="button"
        onClick={onTryAll}
        className="mt-4 inline-flex items-center gap-2 h-9 px-4 rounded-full
                   bg-brand-50 hover:bg-brand-100 text-brand-700 font-extrabold
                   text-[12.5px] ring-1 ring-brand-100 transition-colors"
      >
        <Icon name="grid" className="w-3.5 h-3.5" />
        جست‌وجو در همه بخش‌ها
      </button>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Results panel — grouped by scope                                        */
/* ─────────────────────────────────────────────────────────────────────── */

function ResultsPanel({
  results, query, flatHits, activeIndex, setActiveIndex, onPick, onSeeAll,
}: {
  results: SearchResults;
  query: string;
  flatHits: SearchHit[];
  activeIndex: number;
  setActiveIndex: (i: number) => void;
  onPick: (hit: SearchHit) => void;
  onSeeAll: () => void;
}) {
  let runningIndex = -1; // for accurate keyboard mapping across groups

  return (
    <div>
      {/* Result groups */}
      <div className="p-3 md:p-4 space-y-4">
        {results.scopes
          .filter((g) => g.hits.length > 0)
          .map((g) => (
            <ResultGroup
              key={g.scope}
              group={g}
              query={query}
              indexOffset={(() => { runningIndex += 0; return runningIndex; })()}
              activeIndex={activeIndex}
              setActiveIndex={setActiveIndex}
              onPick={onPick}
              advanceIndex={(n) => { runningIndex += n; }}
              flatHits={flatHits}
            />
          ))}
      </div>

      {/* Footer — see-all + keyboard hints */}
      <div className="px-5 py-3 border-t border-ink-100 flex flex-wrap items-center justify-between gap-3
                      bg-gradient-to-l from-ink-50/60 to-transparent rounded-b-3xl">
        <button
          type="button"
          onClick={onSeeAll}
          className="inline-flex items-center gap-2 text-[12.5px] text-brand-700 font-extrabold
                     hover:gap-3 transition-all"
        >
          مشاهده همه نتایج برای «{query}»
          <Icon name="arrow-left" className="w-3.5 h-3.5" />
        </button>
        <div className="hidden md:flex items-center gap-3 text-[11px] text-ink-400 font-medium">
          <span className="inline-flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> حرکت</span>
          <span className="inline-flex items-center gap-1"><Kbd>↵</Kbd> باز کردن</span>
          <span className="inline-flex items-center gap-1"><Kbd>Esc</Kbd> بستن</span>
        </div>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1
                    rounded text-[10px] font-extrabold text-ink-600
                    bg-white ring-1 ring-ink-200">
      {children}
    </kbd>
  );
}

function ResultGroup({
  group, query, activeIndex, setActiveIndex, onPick, flatHits,
}: {
  group: SearchScopeResult;
  query: string;
  indexOffset: number;        // not used directly — mapping happens via flatHits
  activeIndex: number;
  setActiveIndex: (i: number) => void;
  onPick: (hit: SearchHit) => void;
  advanceIndex: (n: number) => void;
  flatHits: SearchHit[];
}) {
  const meta = SCOPE_META[group.scope];
  const Icn  = SCOPE_ICON[group.scope];
  return (
    <section>
      <header className="flex items-center justify-between mb-2 px-1.5">
        <div className="inline-flex items-center gap-2">
          <span className="w-6 h-6 rounded-lg bg-brand-50 text-brand-600
                           flex items-center justify-center">
            <Icon name={Icn} className="w-3.5 h-3.5" />
          </span>
          <h5 className="text-[12.5px] font-extrabold text-ink-700">
            {meta.label}
            {group.total > group.hits.length && (
              <span className="ms-1.5 text-[10.5px] font-bold text-ink-400 tabular-nums">
                {fa(group.total)} نتیجه
              </span>
            )}
          </h5>
        </div>
        <Link
          href={`${meta.href}?q=${encodeURIComponent(query)}`}
          className="text-[11.5px] text-brand-600 hover:text-brand-700 font-extrabold
                     inline-flex items-center gap-1 group"
        >
          مشاهده همه
          <Icon name="arrow-left" className="w-3 h-3 group-hover:-translate-x-0.5 transition-transform" />
        </Link>
      </header>

      <ul className="space-y-1">
        {group.hits.map((hit) => {
          const fi = flatHits.findIndex((h) => h.id === hit.id);
          const isActive = fi === activeIndex;
          return (
            <li key={hit.id}>
              <button
                type="button"
                role="option"
                aria-selected={isActive}
                onMouseEnter={() => setActiveIndex(fi)}
                onClick={() => onPick(hit)}
                className={`w-full flex items-center gap-3 px-2.5 py-2.5 rounded-2xl text-right
                            transition-all ring-1 ring-transparent
                            ${isActive
                              ? 'bg-brand-50 ring-brand-100'
                              : 'hover:bg-ink-50/70'}`}
              >
                <Thumb hit={hit} />
                <div className="flex-1 min-w-0">
                  <p className="text-[13.5px] font-extrabold text-ink-900 truncate">
                    <Highlight text={hit.title} term={query} />
                  </p>
                  {hit.subtitle && (
                    <p className="mt-0.5 text-[11.5px] text-ink-500 font-medium truncate">
                      {hit.subtitle}
                    </p>
                  )}
                </div>
                {hit.badge && (
                  <span className="hidden sm:inline-flex items-center h-6 px-2 rounded-full
                                   bg-white text-brand-700 ring-1 ring-brand-100
                                   text-[10.5px] font-extrabold tabular-nums shrink-0">
                    {hit.badge}
                  </span>
                )}
                <Icon
                  name="arrow-left"
                  className={`w-3.5 h-3.5 shrink-0 transition-all
                              ${isActive ? 'text-brand-600 -translate-x-0.5' : 'text-ink-300'}`}
                />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Thumb({ hit }: { hit: SearchHit }) {
  if (hit.imageUrl) {
    return (
      <span className="relative w-11 h-11 rounded-xl overflow-hidden ring-1 ring-ink-100 shrink-0 bg-ink-50">
        <Image src={hit.imageUrl} alt="" fill sizes="44px" className="object-cover" />
      </span>
    );
  }
  return (
    <span className="w-11 h-11 rounded-xl bg-gradient-to-br from-brand-50 to-mint-50
                     text-brand-600 flex items-center justify-center shrink-0 ring-1 ring-brand-100">
      <Icon name={SCOPE_ICON[hit.scope]} className="w-5 h-5" />
    </span>
  );
}
