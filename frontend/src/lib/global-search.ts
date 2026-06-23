/**
 * ───────────────────────────────────────────────────────────────────────────
 *  Global Search — backend-faithful omni-search across every public dataset.
 *
 *  Backend contract (apps/<app>/filters.py):
 *
 *    1. madadkar / campaigns      — "?search=" (title A, description B,
 *                                              sponsor.name C; trigram on
 *                                              title/description/sponsor)
 *                                  — optional facets: sponsor_slug, status,
 *                                              has_deadline, is_fully_funded
 *
 *    2. r4j      / criminals      — "?search=" (first_name A, last_name A,
 *                                              slug B, aliases B)
 *                                  — optional facets: country, province,
 *                                              city, gender
 *
 *    3. lms      / courses        — "?search=" (title A, subtitle B,
 *                                              short_description B,
 *                                              description C, instructor C)
 *                                  — optional facets: category, level
 *
 *    4. kindness / listings       — "?search=" (title A, description B,
 *                                              search_document C)
 *                                  — optional facets: listing_type, category,
 *                                              province, city
 *
 *    5. tabyin   / contents       — "?search=" (title A, description B,
 *                                              author_username C)
 *                                  — optional facets: media_type, author
 *
 *    6. support  / knowledge      — "?search=" (icontains title/summary/body)
 *
 *  Everything is GET, public, paginated, returns the envelope:
 *    "{ success, status_code, message, data: { results, count, ... } }"
 *  unwrapped to "{ results, ... }" by apiFetch().
 *
 *  This module aggregates a single user query across all six endpoints in
 *  parallel and shapes the results into a uniform SearchHit for the UI.
 * ───────────────────────────────────────────────────────────────────────────
 */

import { apiFetch } from './api';

/* ───────────────────────────────────────────────────────────────────────── */
/*  Public types                                                              */
/* ───────────────────────────────────────────────────────────────────────── */

export type SearchSource =
  | 'madadkar'
  | 'r4j'
  | 'lms'
  | 'kindness'
  | 'tabyin'
  | 'knowledge';

export type SearchHit = {
  source: SearchSource;
  /** Stable id used as React key */
  id: string;
  title: string;
  /** One-line context shown under the title */
  subtitle?: string;
  /** Optional cover/thumb URL */
  thumb?: string;
  /** Click destination */
  href: string;
  /** Optional badge text (e.g. ۹۸٪، ۱۲ درس، ۲ ساعت) */
  badge?: string;
  /** Pill on the right (مکان / سطح / نوع رسانه) */
  pill?: string;
};

export type SearchSourceMeta = {
  key: SearchSource;
  label: string;
  /** Persian short label used by the source chip */
  shortLabel: string;
  /** Lucide-compatible glyph keyword for the UI */
  glyph:
    | 'campaign'
    | 'gavel'
    | 'graduation'
    | 'heart'
    | 'megaphone'
    | 'book';
  /** Brand-friendly accent (tailwind color tokens) */
  accent: 'brand' | 'rose' | 'amber' | 'mint' | 'sky' | 'violet';
  /** Endpoint the search hits */
  endpoint: string;
  /** Listing page the "see all in <source>" button routes to */
  seeAllHref: (q: string) => string;
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Source registry                                                          */
/* ───────────────────────────────────────────────────────────────────────── */

export const SEARCH_SOURCES: Record<SearchSource, SearchSourceMeta> = {
  madadkar: {
    key: 'madadkar',
    label: 'پشتیبانی مالی جنگ',
    shortLabel: 'حرکت‌ها',
    glyph: 'campaign',
    accent: 'brand',
    endpoint: '/madadkar/campaigns/',
    seeAllHref: (q) => `/madadkar?search=${encodeURIComponent(q)}`,
  },
  r4j: {
    key: 'r4j',
    label: 'جایزه‌ای برای عدالت',
    shortLabel: 'پرونده‌ها',
    glyph: 'gavel',
    accent: 'rose',
    endpoint: '/r4j/criminals/',
    seeAllHref: (q) => `/r4j?search=${encodeURIComponent(q)}`,
  },
  lms: {
    key: 'lms',
    label: 'قرارگاه آموزشی',
    shortLabel: 'دوره‌ها',
    glyph: 'graduation',
    accent: 'amber',
    endpoint: '/lms/courses/',
    seeAllHref: (q) => `/lms?search=${encodeURIComponent(q)}`,
  },
  kindness: {
    key: 'kindness',
    label: 'دیوار مهربانی',
    shortLabel: 'آگهی‌ها',
    glyph: 'heart',
    accent: 'mint',
    endpoint: '/kindness-wall/listings/',
    seeAllHref: (q) => `/kindness-wall?search=${encodeURIComponent(q)}`,
  },
  tabyin: {
    key: 'tabyin',
    label: 'جهاد تبیین',
    shortLabel: 'محتواها',
    glyph: 'megaphone',
    accent: 'violet',
    endpoint: '/tabyin/contents/',
    seeAllHref: (q) => `/tabyin?search=${encodeURIComponent(q)}`,
  },
  knowledge: {
    key: 'knowledge',
    label: 'پایگاه دانش پشتیبانی',
    shortLabel: 'راهنماها',
    glyph: 'book',
    accent: 'sky',
    endpoint: '/support-desk/knowledge/articles/',
    seeAllHref: (q) => `/support?search=${encodeURIComponent(q)}`,
  },
};

export const SEARCH_SOURCE_ORDER: SearchSource[] = [
  'madadkar',
  'r4j',
  'lms',
  'kindness',
  'tabyin',
  'knowledge',
];

/* ───────────────────────────────────────────────────────────────────────── */
/*  Helpers — Persian-friendly text formatters                                */
/* ───────────────────────────────────────────────────────────────────────── */

const LEVEL_LABEL: Record<string, string> = {
  beginner: 'مقدماتی',
  intermediate: 'متوسط',
  advanced: 'پیشرفته',
  professional: 'حرفه‌ای',
};

const MEDIA_LABEL: Record<string, string> = {
  image: 'تصویر',
  video: 'ویدئو',
  audio: 'صوت',
  other: 'سایر',
};

function fa(n: number | undefined | null): string {
  return (n ?? 0).toLocaleString('fa-IR');
}

function formatToman(n: number | undefined | null): string {
  if (!n || n <= 0) return '';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1).replace('.0', '')} میلیارد تومان`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace('.0', '')} میلیون تومان`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} هزار تومان`;
  return `${fa(n)} تومان`;
}

function clean(s: unknown): string {
  if (typeof s !== 'string') return '';
  return s.replace(/\s+/g, ' ').trim();
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Per-source fetchers                                                       */
/* ───────────────────────────────────────────────────────────────────────── */

type Paginated<T> = { results?: T[]; count?: number } | T[];

function unwrap<T>(p: Paginated<T> | null | undefined): T[] {
  if (!p) return [];
  if (Array.isArray(p)) return p;
  return p.results ?? [];
}

const PER_SOURCE_LIMIT = 5;

async function fetchMadadkar(q: string, signal?: AbortSignal): Promise<SearchHit[]> {
  type C = {
    slug: string; title: string; sponsor?: { name?: string };
    progress_percent?: number; deadline?: string;
    cover_image?: string; gallery_images?: { image?: string }[];
    is_fully_funded?: boolean; status_display?: string;
  };
  const data = await apiFetch<Paginated<C>>(
    `/madadkar/campaigns/?search=${encodeURIComponent(q)}&page_size=${PER_SOURCE_LIMIT}`,
    { signal, revalidate: 60 } as never,
  );
  return unwrap(data).slice(0, PER_SOURCE_LIMIT).map((c) => ({
    source: 'madadkar',
    id: `madadkar:${c.slug}`,
    title: clean(c.title) || 'حرکت بدون عنوان',
    subtitle: c.sponsor?.name ? `مددکار: ${clean(c.sponsor.name)}` : undefined,
    thumb: c.cover_image || c.gallery_images?.[0]?.image,
    href: `/madadkar/${c.slug}`,
    badge: typeof c.progress_percent === 'number'
      ? `${fa(Math.round(c.progress_percent))}٪ تأمین شد`
      : undefined,
    pill: c.is_fully_funded ? 'تکمیل شد' : c.status_display,
  }));
}

async function fetchR4J(q: string, signal?: AbortSignal): Promise<SearchHit[]> {
  type P = {
    slug: string; first_name?: string; last_name?: string;
    country?: string; province?: string; city?: string;
    total_bounty_toman?: number; bounties_count?: number;
    primary_photo?: { image?: string };
  };
  const data = await apiFetch<Paginated<P>>(
    `/r4j/criminals/?search=${encodeURIComponent(q)}&page_size=${PER_SOURCE_LIMIT}`,
    { signal, revalidate: 120 } as never,
  );
  return unwrap(data).slice(0, PER_SOURCE_LIMIT).map((p) => {
    const fullName = clean(`${p.first_name ?? ''} ${p.last_name ?? ''}`) || p.slug;
    const loc = [p.city, p.province, p.country].filter(Boolean).join('، ');
    return {
      source: 'r4j',
      id: `r4j:${p.slug}`,
      title: fullName,
      subtitle: loc || undefined,
      thumb: p.primary_photo?.image,
      href: `/r4j/${p.slug}`,
      badge: p.total_bounty_toman ? formatToman(p.total_bounty_toman) : undefined,
      pill: p.bounties_count ? `${fa(p.bounties_count)} جایزه` : undefined,
    };
  });
}

async function fetchLms(q: string, signal?: AbortSignal): Promise<SearchHit[]> {
  type Co = {
    slug: string; title: string; subtitle?: string;
    instructor_name?: string; level?: string;
    cover_image?: string; lessons_count?: number;
    enrollments_count?: number;
  };
  const data = await apiFetch<Paginated<Co>>(
    `/lms/courses/?search=${encodeURIComponent(q)}&page_size=${PER_SOURCE_LIMIT}`,
    { signal, revalidate: 60 } as never,
  );
  return unwrap(data).slice(0, PER_SOURCE_LIMIT).map((c) => ({
    source: 'lms',
    id: `lms:${c.slug}`,
    title: clean(c.title),
    subtitle: c.instructor_name ? `مدرس: ${clean(c.instructor_name)}` : c.subtitle,
    thumb: c.cover_image,
    href: `/lms/courses/${c.slug}`,
    badge: c.lessons_count ? `${fa(c.lessons_count)} درس` : undefined,
    pill: c.level ? LEVEL_LABEL[c.level] ?? c.level : undefined,
  }));
}

async function fetchKindness(q: string, signal?: AbortSignal): Promise<SearchHit[]> {
  type L = {
    slug: string; title: string; listing_type?: 'need_help' | 'offer_help' | string;
    category?: { title?: string }; province?: string; city?: string;
    cover_image?: string; view_count?: number;
  };
  const data = await apiFetch<Paginated<L>>(
    `/kindness-wall/listings/?search=${encodeURIComponent(q)}&page_size=${PER_SOURCE_LIMIT}`,
    { signal, revalidate: 60 } as never,
  );
  return unwrap(data).slice(0, PER_SOURCE_LIMIT).map((l) => {
    const loc = [l.city, l.province].filter(Boolean).join('، ');
    return {
      source: 'kindness',
      id: `kindness:${l.slug}`,
      title: clean(l.title),
      subtitle: [l.category?.title, loc].filter(Boolean).join(' · ') || undefined,
      thumb: l.cover_image,
      href: `/kindness-wall/${l.slug}`,
      badge: l.view_count ? `${fa(l.view_count)} بازدید` : undefined,
      pill: l.listing_type === 'need_help'
        ? 'نیازمند کمک'
        : l.listing_type === 'offer_help'
          ? 'پیشنهاد کمک'
          : undefined,
    };
  });
}

async function fetchTabyin(q: string, signal?: AbortSignal): Promise<SearchHit[]> {
  type T = {
    external_id: string; title?: string; description?: string;
    author_username?: string; primary_media_type?: string;
    attachments?: { url?: string; media_type?: string }[];
    origin?: string;
  };
  const data = await apiFetch<Paginated<T>>(
    `/tabyin/contents/?search=${encodeURIComponent(q)}&page_size=${PER_SOURCE_LIMIT}`,
    { signal, revalidate: 60 } as never,
  );
  return unwrap(data).slice(0, PER_SOURCE_LIMIT).map((t) => {
    const image = t.attachments?.find((a) => a.media_type === 'image')?.url
              ?? t.attachments?.[0]?.url;
    return {
      source: 'tabyin',
      id: `tabyin:${t.external_id}`,
      title: clean(t.title) || (t.description ? clean(t.description).slice(0, 60) + '…' : 'محتوای تبیینی'),
      subtitle: t.author_username ? `@${clean(t.author_username)}` : undefined,
      thumb: image,
      href: `/tabyin/${t.external_id}`,
      pill: t.primary_media_type
        ? MEDIA_LABEL[t.primary_media_type] ?? t.primary_media_type
        : undefined,
      badge: t.origin === 'user_submitted' ? 'مردمی' : undefined,
    };
  });
}

async function fetchKnowledge(q: string, signal?: AbortSignal): Promise<SearchHit[]> {
  type K = {
    slug: string; title: string; summary?: string;
    category?: { title?: string };
  };
  const data = await apiFetch<Paginated<K>>(
    `/support-desk/knowledge/articles/?search=${encodeURIComponent(q)}&page_size=${PER_SOURCE_LIMIT}`,
    { signal, revalidate: 300 } as never,
  );
  return unwrap(data).slice(0, PER_SOURCE_LIMIT).map((a) => ({
    source: 'knowledge',
    id: `knowledge:${a.slug}`,
    title: clean(a.title),
    subtitle: clean(a.summary) || undefined,
    href: `/support/knowledge/${a.slug}`,
    pill: a.category?.title,
  }));
}

const FETCHERS: Record<SearchSource, (q: string, signal?: AbortSignal) => Promise<SearchHit[]>> = {
  madadkar: fetchMadadkar,
  r4j: fetchR4J,
  lms: fetchLms,
  kindness: fetchKindness,
  tabyin: fetchTabyin,
  knowledge: fetchKnowledge,
};

/* ───────────────────────────────────────────────────────────────────────── */
/*  Aggregator                                                                */
/* ───────────────────────────────────────────────────────────────────────── */

export type SearchAggregate = {
  q: string;
  /** Hits grouped by source, only sources that returned ≥1 hit are present. */
  groups: { source: SearchSource; hits: SearchHit[] }[];
  /** Total hits across every source. */
  total: number;
  /** Sources that errored (network / 4xx / 5xx) — UI may surface a quiet note. */
  errored: SearchSource[];
};

export async function searchAll(
  q: string,
  opts?: { sources?: SearchSource[]; signal?: AbortSignal },
): Promise<SearchAggregate> {
  const cleaned = (q ?? '').trim();
  const empty: SearchAggregate = { q: cleaned, groups: [], total: 0, errored: [] };
  if (!cleaned || cleaned.length < 2) return empty;

  const wanted = opts?.sources ?? SEARCH_SOURCE_ORDER;
  const settled = await Promise.allSettled(
    wanted.map((src) => FETCHERS[src](cleaned, opts?.signal)),
  );

  const groups: SearchAggregate['groups'] = [];
  const errored: SearchSource[] = [];
  let total = 0;
  settled.forEach((result, idx) => {
    const src = wanted[idx];
    if (result.status === 'fulfilled') {
      if (result.value.length) {
        groups.push({ source: src, hits: result.value });
        total += result.value.length;
      }
    } else {
      const reason = result.reason as { name?: string } | undefined;
      if (reason?.name !== 'AbortError') errored.push(src);
    }
  });

  groups.sort(
    (a, b) =>
      SEARCH_SOURCE_ORDER.indexOf(a.source) - SEARCH_SOURCE_ORDER.indexOf(b.source),
  );

  return { q: cleaned, groups, total, errored };
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Recent searches — client-side cache (localStorage)                        */
/* ───────────────────────────────────────────────────────────────────────── */

const STORAGE_KEY = 'sj.recent-searches';
const MAX_RECENT = 6;

export function loadRecent(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === 'string').slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

export function pushRecent(q: string): string[] {
  if (typeof window === 'undefined') return [];
  const cleaned = (q ?? '').trim();
  if (!cleaned) return loadRecent();
  const list = [cleaned, ...loadRecent().filter((x) => x !== cleaned)].slice(0, MAX_RECENT);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    /* localStorage may be disabled (private mode) — silently ignore */
  }
  return list;
}

export function clearRecent(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* no-op */
  }
}

/* ───────────────────────────────────────────────────────────────────────── */
/*  Default suggestions — shown when the field is empty                        */
/* ───────────────────────────────────────────────────────────────────────── */

export const TRENDING_QUERIES: { label: string; q: string; source?: SearchSource }[] = [
  { label: 'حرکت‌های فعال',     q: 'فعال',          source: 'madadkar' },
  { label: 'دوره‌های امداد',    q: 'امداد',         source: 'lms' },
  { label: 'پرونده‌های ویژه',   q: '',              source: 'r4j' },
  { label: 'نیازمند کمک',       q: 'نیازمند',       source: 'kindness' },
  { label: 'روایت‌های مردمی',   q: 'مردمی',         source: 'tabyin' },
  { label: 'راهنمای ثبت‌نام',   q: 'ثبت‌نام',       source: 'knowledge' },
];
