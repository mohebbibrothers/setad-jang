'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { PlayCircle, Award, Clock, ArrowLeft } from 'lucide-react';

type Course = {
  slug: string;
  title: string;
  level: string;
  duration: string;
  tone: 'a' | 'b' | 'c' | 'd';
};

const COURSES: Course[] = [
  { slug: 'fillm-namayi',    title: 'فیلم‌نامه‌نویسی حرفه‌ای جهادی', level: 'متوسط',   duration: '۸ ساعت',  tone: 'a' },
  { slug: 'cinematography',  title: 'فیلم‌نامه‌نویسی و فیلم‌سازی فرهنگی', level: 'پیشرفته', duration: '۱۲ ساعت', tone: 'b' },
  { slug: 'media-lit',       title: 'سواد رسانه‌ای و جنگ ادراکی',     level: 'مقدماتی', duration: '۶ ساعت',  tone: 'c' },
  { slug: 'web-design',      title: 'آموزش کامل طراحی سایت',        level: 'پیشرفته', duration: '۲۴ ساعت', tone: 'd' },
];

const TONE_BG: Record<Course['tone'], string> = {
  a: 'from-amber-500 to-orange-700',
  b: 'from-rose-500 to-rose-800',
  c: 'from-brand-500 to-brand-800',
  d: 'from-violet-500 to-violet-800',
};

export function LearningShowcase() {
  return (
    <section className="section-y bg-gradient-to-b from-white to-brand-50/40">
      <div className="container-edge">
        <div className="flex items-end justify-between gap-6 mb-10">
          <div>
            <span className="eyebrow">مدرسه آموزشی بعثت مردم</span>
            <h2 className="mt-4 text-3xl md:text-4xl font-extrabold text-ink-900">
              یاد بگیرید، عمل کنید، گواهی بگیرید
            </h2>
            <p className="mt-3 text-ink-600 max-w-xl leading-8">
              دوره‌های آموزشی با کوییز نهایی و گواهی قابل استعلام عمومی.
            </p>
          </div>
          <Link href="/lms" className="hidden md:inline-flex btn-outline btn-md">
            مشاهده همه دوره‌ها <ArrowLeft className="w-4 h-4" />
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {COURSES.map((c, i) => (
            <motion.article
              key={c.slug}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, delay: i * 0.06 }}
              className="card overflow-hidden group"
            >
              <Link href={`/lms/courses/${c.slug}`} className="block">
                <div className={`relative aspect-[4/5] bg-gradient-to-br ${TONE_BG[c.tone]} overflow-hidden`}>
                  <div className="absolute inset-0 bg-grid-pattern opacity-25" />
                  <div className="absolute inset-0 flex items-center justify-center
                                  transition-transform duration-500 group-hover:scale-110">
                    <PlayCircle className="w-20 h-20 text-white/80" strokeWidth={1.5} />
                  </div>
                  <div className="absolute bottom-0 inset-x-0 p-4
                                  bg-gradient-to-t from-black/55 to-transparent text-white">
                    <p className="text-lg font-bold leading-7">{c.title}</p>
                  </div>
                </div>
                <div className="p-4 flex items-center justify-between text-sm">
                  <span className="inline-flex items-center gap-1.5 text-ink-600">
                    <Clock className="w-4 h-4" /> {c.duration}
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-brand-700 font-semibold">
                    <Award className="w-4 h-4" /> {c.level}
                  </span>
                </div>
              </Link>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
