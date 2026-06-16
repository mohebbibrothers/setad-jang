'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useState } from 'react';
import { motion } from 'framer-motion';
import { Plus } from 'lucide-react';
import { SectionTitle } from './SectionTitle';

/**
 * Backend contract (apps/lms):
 *   GET /api/v1/lms/categories/
 *   GET /api/v1/lms/courses/?category={slug}
 *
 * Each course: slug, title, instructor, cover_image_url, is_new, level, duration
 */
export type CourseCard = {
  slug: string;
  title: string;
  instructor?: string;
  coverUrl?: string;
  isNew?: boolean;
  toneFrom?: string;     // fallback gradient (when no cover)
  toneTo?: string;
};

export type EduCategory = { slug: string; name: string };

const DEFAULT_TABS: EduCategory[] = [
  { slug: 'all',      name: 'همه آموزش‌ها' },
  { slug: 'rescue',   name: 'امداد و نجات' },
  { slug: 'security', name: 'موارد امنیتی' },
];

export function EducationSection({
  categories = DEFAULT_TABS,
  courses,
}: {
  categories?: EduCategory[];
  courses: CourseCard[];
}) {
  const [active, setActive] = useState(categories[0].slug);

  return (
    <section className="section-y bg-white" id="education">
      <div className="container-edge">
        <SectionTitle
          title="قرارگاه آموزشی"
          description="دوره‌های جهادی، تخصصی و فرهنگی همراه با کوییز نهایی و گواهی استعلام‌پذیر."
        />

        {/* Tabs */}
        <div
          role="tablist"
          className="flex items-center justify-center gap-1 border-b border-ink-100 mb-8 overflow-x-auto no-scrollbar"
        >
          {categories.map((c) => (
            <button
              key={c.slug}
              role="tab"
              aria-selected={active === c.slug}
              onClick={() => setActive(c.slug)}
              className={`relative px-4 md:px-6 py-3 text-[14px] md:text-[15px] font-semibold whitespace-nowrap
                          transition-colors ${
                            active === c.slug
                              ? 'text-brand-600'
                              : 'text-ink-500 hover:text-ink-800'
                          }`}
            >
              {c.name}
              {active === c.slug && (
                <motion.span
                  layoutId="edu-tab"
                  className="absolute inset-x-2 -bottom-px h-[3px] rounded-full bg-brand-500"
                />
              )}
            </button>
          ))}
        </div>

        {/* Course grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 md:gap-5">
          {courses.map((c, i) => (
            <motion.article
              key={c.slug}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ duration: 0.4, delay: i * 0.06 }}
              className="group"
            >
              <Link
                href={`/lms/courses/${c.slug}`}
                className="relative block rounded-2xl overflow-hidden aspect-[4/5]
                           shadow-soft hover:shadow-card hover:-translate-y-1
                           transition-all duration-300 bg-ink-200"
              >
                {c.coverUrl ? (
                  <Image
                    src={c.coverUrl}
                    alt={c.title}
                    fill
                    sizes="(max-width: 768px) 45vw, 22vw"
                    className="object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                ) : (
                  <div
                    className="w-full h-full"
                    style={{ background: `linear-gradient(135deg, ${c.toneFrom || '#0D8074'}, ${c.toneTo || '#053832'})` }}
                  />
                )}
                <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-transparent" />
                {c.isNew && (
                  <span className="absolute top-3 right-3 inline-flex items-center px-3 h-7 rounded-full
                                   bg-mint-500 text-white text-[11px] font-bold shadow-soft">
                    جدید
                  </span>
                )}
                {(c.instructor || c.title) && (
                  <div className="absolute inset-x-0 bottom-0 p-3 text-white">
                    {c.instructor && <p className="text-[11px] opacity-90 mb-0.5">{c.instructor}</p>}
                    <p className="text-[13px] font-bold leading-5 line-clamp-2 drop-shadow">{c.title}</p>
                  </div>
                )}
              </Link>
            </motion.article>
          ))}
        </div>

        {/* "+ جدید" mint CTA */}
        <div className="flex justify-center mt-8">
          <Link
            href="/lms"
            className="inline-flex items-center gap-2 h-12 px-8 rounded-full
                       bg-mint-500 hover:bg-mint-600 text-white font-bold
                       shadow-soft transition-colors"
          >
            <Plus className="w-4 h-4" />
            جدید
          </Link>
        </div>
      </div>
    </section>
  );
}
