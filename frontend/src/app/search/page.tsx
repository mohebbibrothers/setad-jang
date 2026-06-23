import type { Metadata } from 'next';
import Link from 'next/link';
import Image from 'next/image';
import { Suspense } from 'react';
import {
  searchAll,
  SEARCH_SOURCES,
  SEARCH_SOURCE_ORDER,
  type SearchSource,
} from '@/lib/global-search';
import { GlobalSearch } from '@/components/home/GlobalSearch';

/**
 * Full-page search results — server-rendered against the same omni-search
 * pipeline used by the homepage hero bar. Lets users land here from
 * `Enter` in the search pill (or from `/search?q=&source=`) and browse
 * every matching hit grouped by source.
 */
export const dynamic = 'force-dynamic';

type SP = { q?: string; source?: string };

export async function generateMetadata({
  searchParams,
}: { searchParams: Promise<SP> }): Promise<Metadata> {
  const sp = await searchParams;
  const q = (sp?.q ?? '').trim();
  return {
    title: q ? `جست‌وجو: ${q}` : 'جست‌وجو در سامانه',
    description: q
      ? `نتایج جست‌وجو برای «${q}» در بعثت مردم — حرکت‌های مالی جنگ، پرونده‌های عدالت، دوره‌ها، آگهی‌های مهربانی، تبیین و دانش.`
      : 'جست‌وجوی سراسری در همه‌ی بخش‌های سامانه بعثت مردم.',
    robots: q ? { index: false, follow: true } : undefined,
  };
}

export default async function SearchPage({
  searchParams,
}: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const q = (sp?.q ?? '').trim();
  const sourceParam = (sp?.source ?? '') as SearchSource | '';
  const sources = sourceParam && (SEARCH_SOURCE_ORDER as string[]).includes(sourceParam)
    ? [sourceParam as SearchSource]
    : undefined;

  const data = q.length >= 2
    ? await searchAll(q, { sources })
    : { q, groups: [], total: 0, errored: [] as SearchSource[] };

  return (
    <section className="bg-white">
      {/* Inline (non-overlapping) variant of the search bar at the top */}
      <div className="container-edge pt-8 pb-4">
        <Suspense>
          <GlobalSearch variant="inline" initialQuery={q} />
        </Suspense>

        <div className="mt-6 flex items-center justify-between gap-3 flex-wrap">
          <h1 className="text-[18px] md:text-[22px] font-extrabold text-ink-900">
            {q
              ? <>نتایج جست‌وجو برای «<span className="text-brand-700">{q}</span>»</>
              : 'برای شروع، عبارتی را در نوار جست‌وجو وارد کنید'}
          </h1>
          {q && (
            <span className="text-[12.5px] font-bold text-ink-500 tabular-nums">
              {data.total.toLocaleString('fa-IR')} نتیجه
            </span>
          )}
        </div>
      </div>

      <div className="container-edge pb-16">
        {q.length < 2 ? (
          <EmptyHint />
        ) : data.total === 0 ? (
          <NoResults q={q} />
        ) : (
          <div className="space-y-10">
            {data.groups.map((g) => {
              const meta = SEARCH_SOURCES[g.source];
              return (
                <div key={g.source}>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-[15px] md:text-[16px] font-extrabold text-ink-900">
                      {meta.label}
                      <span className="text-ink-400 font-bold mr-2">
                        ({g.hits.length.toLocaleString('fa-IR')})
                      </span>
                    </h2>
                    <Link
                      href={meta.seeAllHref(q)}
                      className="text-[12.5px] font-extrabold text-brand-700 hover:text-brand-800"
                    >
                      مشاهده همه در {meta.shortLabel} ←
                    </Link>
                  </div>

                  <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-4">
                    {g.hits.map((h) => (
                      <li key={h.id}>
                        <Link
                          href={h.href}
                          className="group flex items-center gap-3 p-3 rounded-2xl
                                     bg-white ring-1 ring-ink-100 hover:ring-brand-200
                                     hover:shadow-[0_14px_30px_-18px_rgba(11,53,48,.25)]
                                     transition-all duration-200"
                        >
                          <span className="relative shrink-0 w-14 h-14 rounded-xl overflow-hidden bg-ink-100">
                            {h.thumb ? (
                              <Image
                                src={h.thumb}
                                alt=""
                                fill
                                sizes="56px"
                                className="object-cover"
                              />
                            ) : (
                              <span className="absolute inset-0 bg-gradient-to-br from-brand-50 to-brand-100" />
                            )}
                          </span>
                          <span className="flex-1 min-w-0">
                            <span className="block text-[13.5px] font-extrabold text-ink-900 truncate">
                              {h.title}
                            </span>
                            {h.subtitle && (
                              <span className="block text-[11.5px] text-ink-500 truncate mt-0.5">
                                {h.subtitle}
                              </span>
                            )}
                            {(h.badge || h.pill) && (
                              <span className="mt-1.5 flex items-center gap-1.5 text-[11px] font-bold">
                                {h.pill && (
                                  <span className="inline-flex items-center px-2 h-5 rounded-full
                                                   bg-brand-50 text-brand-700">
                                    {h.pill}
                                  </span>
                                )}
                                {h.badge && (
                                  <span className="text-ink-600">{h.badge}</span>
                                )}
                              </span>
                            )}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

function EmptyHint() {
  return (
    <div className="text-center py-16">
      <div className="mx-auto mb-4 w-16 h-16 rounded-2xl
                      bg-gradient-to-br from-brand-50 to-brand-100 text-brand-600
                      flex items-center justify-center">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor"
             strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      </div>
      <p className="text-[15px] font-extrabold text-ink-900">
        نوار جست‌وجو در بالای صفحه آماده است
      </p>
      <p className="text-[12.5px] text-ink-500 mt-2 leading-7 max-w-md mx-auto">
        می‌توانید عبارت موردنظر خود را تایپ کنید تا نتایج زنده از همه‌ی بخش‌های سامانه نمایش داده شود.
      </p>
    </div>
  );
}

function NoResults({ q }: { q: string }) {
  return (
    <div className="text-center py-16">
      <div className="mx-auto mb-4 w-16 h-16 rounded-2xl
                      bg-gradient-to-br from-rose-50 to-rose-100 text-rose-600
                      flex items-center justify-center">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor"
             strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      </div>
      <p className="text-[15px] font-extrabold text-ink-900">
        نتیجه‌ای برای «{q}» پیدا نشد
      </p>
      <p className="text-[12.5px] text-ink-500 mt-2 leading-7 max-w-md mx-auto">
        لطفاً عبارت را کوتاه‌تر، متفاوت‌تر یا با املای دیگری بنویسید، یا فیلتر منبع را تغییر دهید.
      </p>
    </div>
  );
}
