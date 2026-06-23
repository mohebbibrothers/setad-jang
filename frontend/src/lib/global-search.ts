/**
 * Global Search — multi-domain backend-faithful client.
 *
 * Maps the hero's universal search bar onto the five public list endpoints
 * exposed by the Django backend. Every endpoint already supports a
 * `?search=` query parameter wired to `apps.core.search.apply_smart_search`
 * (PostgreSQL FTS + trigram, SQLite icontains fallback) — see:
 *
 *   apps/madadkar/filters.py     → CampaignPublicFilter.filter_search
 *   apps/r4j/filters.py          → R4JCriminalPublicFilter.filter_search
 *   apps/lms/filters.py          → CoursePublicFilter.filter_search
 *   apps/kindness_wall/filters.py→ KindnessListingPublicFilter.filter_search
 *   apps/tabyin/filters.py       → PublicTabyinContentFilter.filter_search
 *
 * Each scope fetches a small slice (`page_size=4`) in parallel so the
 * dropdown stays snappy. Errors per scope are isolated — one slow domain
 * never blocks the rest.
 */

import { apiFetch } from './api';

/* ─────────────────────────────────────────────────────────────────────── */
/*  Public scope contract                                                  */
/* ─────────────────────────────────────────────────────────────────────── */

export type SearchScope =
  | 'all'        // fan-out to every scope
  | 'campaign'   // madadkar
  | 'criminal'   // r4j
  | 'course'     // lms
  | 'listing'    // kindness wall
  | 'tabyin';    // jihad-e tabyin

export type SearchHit = {
  /** Stable per-scope key — used as React key. */
  id: string;
  scope: Exclude<SearchScope, 'all'>;
  title: string;
  /** One-line subtitle: sponsor / instructor / category etc. */
  subtitle?: string;
  /** Image thumb URL when the backend provides one. */
  imageUrl?: string;
  /** Optional badge text (e.g. مبلغ کل، تعداد فراگیر، شهر). */
  badge?: string;
  /** Internal route the hit links to. */
  href: string;
};

export type SearchScopeResult = {
  scope: Exclude<SearchScope, 'all'>;
  hits: SearchHit[];
  total: number;
  ok: boolean;
};

export type SearchResults = {
  query: string;
  scopes: SearchScopeResult[];
  /** Overall hit count across every scope. */
  total: number;
};

/* ─────────────────────────────────────────────────────────────────────── */
/*  Scope metadata — used by chip strip + group headers                     */
/* ─────────────────────────────────────────────────────────────────────── */

export const SCOPE_META: Record<Exclude<SearchScope, 'all'>, {
  label: string;
  short: string;
  iconKey: 'warfund' | 'r4j' | 'lms' | 'kindness' | 'tabyin';
  href: string;          // see-all target
  tone: string;          // CSS-class fragment for chip tinting
}> = {
  campaign: { label: 'پشتیبانی مالی جنگ', short: 'حرکت‌ها',     iconKey: 'warfund',  href: '/madadkar',      tone: 'campaign'  },
  criminal: { label: 'جایزه برای عدالت', short: 'پرونده‌ها',    iconKey: 'r4j',      href: '/r4j',           tone: 'criminal'  },
  course:   { label: 'قرارگاه آموزشی',   short: 'دوره‌ها',      iconKey: 'lms',      href: '/lms',           tone: 'course'    },
  listing:  { label: 'دیوار مهربانی',    short: 'آگهی‌ها',      iconKey: 'kindness', href: '/kindness-wall', tone: 'kindness'  },
  tabyin:   { label: 'جهاد تبیین',       short: 'محتواها',      iconKey: 'tabyin',   href: '/tabyin',        tone: 'tabyin'    },
};

export const SCOPE_ORDER: Array<Exclude<SearchScope, 'all'>> = [
  'campaign', 'criminal', 'course', 'listing', 'tabyin',
];

/* ─────────────────────────────────────────────────────────────────────── */
/*  Persian number helper (kept local — no util import to keep tree-shake)  */
/* ─────────────────────────────────────────────────────────────────────── */

function fa(n: number | string): string {
  return Number(n).toLocaleString('fa-IR');
}

function tomanShort(toman: number | undefined | null): string | undefined {
  if (!toman || toman <= 0) return undefined;
  if (toman >= 1_000_000_000) return `${fa((toman / 1_000_000_000).toFixed(1))} میلیارد تومان`;
  if (toman >= 1_000_000)     return `${fa((toman / 1_000_000).toFixed(1))} میلیون تومان`;
  if (toman >= 1_000)         return `${fa((toman / 1_000).toFixed(0))} هزار تومان`;
  return `${fa(toman)} تومان`;
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Server contracts (subset — only what the dropdown displays)            */
/* ─────────────────────────────────────────────────────────────────────── */

type Paginated<T> = { results?: T[]; count?: number } | T[];
function unwrap<T>(p: Paginated<T> | null | undefined): { list: T[]; count: number } {
  if (!p) return { list: [], count: 0 };
  if (Array.isArray(p)) return { list: p, count: p.length };
  return { list: p.results ?? [], count: p.count ?? (p.results?.length ?? 0) };
}

type ApiCampaign = {
  slug: string; title: string; cover_image?: string | null;
  sponsor?: { name?: string } | null;
  total_amount?: number; participant_count?: number;
  status_display?: string;
};
type ApiCriminal = {
  slug: string; first_name?: string; last_name?: string;
  country?: string; province?: string; city?: string;
  primary_photo?: { image?: string } | null;
  total_bounty_toman?: number;
};
type ApiCourse = {
  slug: string; title: string; subtitle?: string;
  cover_image?: string | null; instructor_name?: string;
  level?: string; enrollments_count?: number;
};
type ApiListing = {
  slug: string; title: string; cover_image?: string | null;
  listing_type?: string;
  category?: { title?: string } | null;
  province?: string; city?: string;
};
type ApiTabyin = {
  external_id: string; title?: string; description?: string;
  primary_media_type?: 'image' | 'video' | 'audio' | 'other';
  attachments?: Array<{ url?: string; media_type?: string }>;
  author_username?: string;
};

/* ─────────────────────────────────────────────────────────────────────── */
/*  Per-scope adapters                                                      */
/* ─────────────────────────────────────────────────────────────────────── */

const PER_SCOPE_SIZE = 4;

async function fetchCampaigns(q: string, signal?: AbortSignal): Promise<SearchScopeResult> {
  try {
    const data = await apiFetch<Paginated<ApiCampaign>>(
      `/madadkar/campaigns/?search=${encodeURIComponent(q)}&page_size=${PER_SCOPE_SIZE}`,
      { signal },
    );
    const { list, count } = unwrap(data);
    return {
      scope: 'campaign', ok: true, total: count,
      hits: list.map<SearchHit>((c) => ({
        id: `campaign:${c.slug}`,
        scope: 'campaign',
        title: c.title,
        subtitle: [c.sponsor?.name, c.status_display].filter(Boolean).join(' · ') || undefined,
        imageUrl: c.cover_image ?? undefined,
        badge: tomanShort(c.total_amount),
        href: `/madadkar/${c.slug}`,
      })),
    };
  } catch {
    return { scope: 'campaign', ok: false, hits: [], total: 0 };
  }
}

async function fetchCriminals(q: string, signal?: AbortSignal): Promise<SearchScopeResult> {
  try {
    const data = await apiFetch<Paginated<ApiCriminal>>(
      `/r4j/criminals/?search=${encodeURIComponent(q)}&page_size=${PER_SCOPE_SIZE}`,
      { signal },
    );
    const { list, count } = unwrap(data);
    return {
      scope: 'criminal', ok: true, total: count,
      hits: list.map<SearchHit>((c) => ({
        id: `criminal:${c.slug}`,
        scope: 'criminal',
        title: `${c.first_name ?? ''} ${c.last_name ?? ''}`.trim() || c.slug,
        subtitle: [c.country, c.province, c.city].filter(Boolean).join(' · ') || undefined,
        imageUrl: c.primary_photo?.image ?? undefined,
        badge: tomanShort(c.total_bounty_toman),
        href: `/r4j/${c.slug}`,
      })),
    };
  } catch {
    return { scope: 'criminal', ok: false, hits: [], total: 0 };
  }
}

const LEVEL_FA: Record<string, string> = {
  beginner: 'مقدماتی', intermediate: 'متوسط', advanced: 'پیشرفته', professional: 'حرفه‌ای',
};

async function fetchCourses(q: string, signal?: AbortSignal): Promise<SearchScopeResult> {
  try {
    const data = await apiFetch<Paginated<ApiCourse>>(
      `/lms/courses/?search=${encodeURIComponent(q)}&page_size=${PER_SCOPE_SIZE}`,
      { signal },
    );
    const { list, count } = unwrap(data);
    return {
      scope: 'course', ok: true, total: count,
      hits: list.map<SearchHit>((c) => ({
        id: `course:${c.slug}`,
        scope: 'course',
        title: c.title,
        subtitle: [c.instructor_name && `مدرس: ${c.instructor_name}`,
                   c.level && LEVEL_FA[c.level]].filter(Boolean).join(' · ') || c.subtitle || undefined,
        imageUrl: c.cover_image ?? undefined,
        badge: c.enrollments_count && c.enrollments_count > 0
          ? `${fa(c.enrollments_count)} فراگیر` : undefined,
        href: `/lms/courses/${c.slug}`,
      })),
    };
  } catch {
    return { scope: 'course', ok: false, hits: [], total: 0 };
  }
}

async function fetchListings(q: string, signal?: AbortSignal): Promise<SearchScopeResult> {
  try {
    const data = await apiFetch<Paginated<ApiListing>>(
      `/kindness-wall/listings/?search=${encodeURIComponent(q)}&page_size=${PER_SCOPE_SIZE}`,
      { signal },
    );
    const { list, count } = unwrap(data);
    return {
      scope: 'listing', ok: true, total: count,
      hits: list.map<SearchHit>((l) => ({
        id: `listing:${l.slug}`,
        scope: 'listing',
        title: l.title,
        subtitle: [l.category?.title, l.province, l.city].filter(Boolean).join(' · ') || undefined,
        imageUrl: l.cover_image ?? undefined,
        badge: l.listing_type === 'offer_help' ? 'ارائه کمک'
             : l.listing_type === 'need_help'  ? 'درخواست کمک' : undefined,
        href: `/kindness-wall/${l.slug}`,
      })),
    };
  } catch {
    return { scope: 'listing', ok: false, hits: [], total: 0 };
  }
}

async function fetchTabyin(q: string, signal?: AbortSignal): Promise<SearchScopeResult> {
  try {
    const data = await apiFetch<Paginated<ApiTabyin>>(
      `/tabyin/contents/?search=${encodeURIComponent(q)}&page_size=${PER_SCOPE_SIZE}`,
      { signal },
    );
    const { list, count } = unwrap(data);
    return {
      scope: 'tabyin', ok: true, total: count,
      hits: list.map<SearchHit>((t) => {
        const cover = t.attachments?.find((a) => a.media_type === 'image')?.url
                   ?? t.attachments?.[0]?.url;
        return {
          id: `tabyin:${t.external_id}`,
          scope: 'tabyin',
          title: t.title || (t.description?.slice(0, 60) ?? 'محتوای تبیینی'),
          subtitle: [t.author_username && `از: ${t.author_username}`,
                     t.primary_media_type && ({
                       image: 'تصویر', video: 'ویدئو', audio: 'صوت', other: 'سایر',
                     } as const)[t.primary_media_type]]
                   .filter(Boolean).join(' · ') || undefined,
          imageUrl: cover ?? undefined,
          href: `/tabyin/${t.external_id}`,
        };
      }),
    };
  } catch {
    return { scope: 'tabyin', ok: false, hits: [], total: 0 };
  }
}

const FETCHERS: Record<Exclude<SearchScope, 'all'>, typeof fetchCampaigns> = {
  campaign: fetchCampaigns,
  criminal: fetchCriminals,
  course:   fetchCourses,
  listing:  fetchListings,
  tabyin:   fetchTabyin,
};

/* ─────────────────────────────────────────────────────────────────────── */
/*  Public API                                                              */
/* ─────────────────────────────────────────────────────────────────────── */

/**
 * Run a query across one or all scopes in parallel.
 * Returns a stable `SearchResults` shape — partial failures never throw.
 */
export async function globalSearch(
  query: string,
  scope: SearchScope = 'all',
  signal?: AbortSignal,
): Promise<SearchResults> {
  const q = (query ?? '').trim();
  if (!q) return { query: '', scopes: [], total: 0 };

  const scopes: Array<Exclude<SearchScope, 'all'>> = scope === 'all'
    ? SCOPE_ORDER
    : [scope];

  const results = await Promise.all(scopes.map((s) => FETCHERS[s](q, signal)));
  const total = results.reduce((a, r) => a + r.hits.length, 0);
  return { query: q, scopes: results, total };
}

/* ─────────────────────────────────────────────────────────────────────── */
/*  Recent + trending — client-side helpers                                 */
/* ─────────────────────────────────────────────────────────────────────── */

const RECENT_KEY = 'sj_recent_searches_v1';
const RECENT_MAX = 6;

export function getRecentSearches(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as unknown;
    return Array.isArray(list) ? list.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export function pushRecentSearch(q: string): string[] {
  if (typeof window === 'undefined') return [];
  const cleaned = (q ?? '').trim();
  if (!cleaned) return getRecentSearches();
  const current = getRecentSearches().filter((x) => x !== cleaned);
  current.unshift(cleaned);
  const next = current.slice(0, RECENT_MAX);
  try { window.localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* noop */ }
  return next;
}

export function clearRecentSearches(): void {
  if (typeof window === 'undefined') return;
  try { window.localStorage.removeItem(RECENT_KEY); } catch { /* noop */ }
}

/** Curated trending queries — surface when the input is empty. */
export const TRENDING_QUERIES: string[] = [
  'پشتیبانی غزه',
  'جانبازان',
  'مهارت رسانه',
  'پدافند سایبری',
  'جنایت‌های جنگی',
  'کمک‌های مردمی',
];
