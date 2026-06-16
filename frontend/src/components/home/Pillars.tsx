'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  HandHeart,
  GraduationCap,
  Megaphone,
  ScrollText,
  Scale,
  LifeBuoy,
  ArrowLeft,
} from 'lucide-react';

const PILLARS = [
  {
    href: '/madadkar',
    title: 'مددکاری',
    desc: 'مشارکت سهم‌محور در کمپین‌های خیریه با شفافیت کامل مالی.',
    Icon: HandHeart,
    tint: 'from-rose-50 to-rose-100 text-rose-600',
    pill: 'bg-rose-500',
  },
  {
    href: '/lms',
    title: 'مدرسه آموزشی',
    desc: 'دوره‌های جهادی و تخصصی همراه با کوییز، گواهی و رتبه‌بندی.',
    Icon: GraduationCap,
    tint: 'from-indigo-50 to-indigo-100 text-indigo-600',
    pill: 'bg-indigo-500',
  },
  {
    href: '/tabyin',
    title: 'جهاد تبیین',
    desc: 'بانک محتوای رسانه‌ای برای روشنگری و مقابله با جنگ ادراکی.',
    Icon: Megaphone,
    tint: 'from-brand-50 to-brand-100 text-brand-600',
    pill: 'bg-brand-500',
  },
  {
    href: '/public-reports',
    title: 'گزارش مردمی',
    desc: 'ثبت گزارش‌های مردمی با پیگیری شفاف و حفظ حریم خصوصی.',
    Icon: ScrollText,
    tint: 'from-amber-50 to-amber-100 text-amber-700',
    pill: 'bg-amber-500',
  },
  {
    href: '/r4j',
    title: 'جایزه عدالت',
    desc: 'معرفی مجرمان و جنایتکاران بین‌المللی و سامانه جوایز عدالت.',
    Icon: Scale,
    tint: 'from-violet-50 to-violet-100 text-violet-600',
    pill: 'bg-violet-500',
  },
  {
    href: '/kindness-wall',
    title: 'دیوار مهربانی',
    desc: 'محل اعلام نیاز و کمک مردمی، بدون خرید و فروش، با هم‌تطبیق هوشمند.',
    Icon: LifeBuoy,
    tint: 'from-emerald-50 to-emerald-100 text-emerald-600',
    pill: 'bg-emerald-500',
  },
] as const;

export function Pillars() {
  return (
    <section className="section-y bg-white relative" id="pillars">
      <div className="container-edge">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <span className="eyebrow">ستون‌های بعثت مردم</span>
          <h2 className="mt-4 text-3xl md:text-4xl font-extrabold text-ink-900">
            هر بخش، یک مأموریت مستقل و یکپارچه
          </h2>
          <p className="mt-3 text-ink-600 leading-8">
            از مشارکت مالی شفاف تا روشنگری رسانه‌ای، آموزش جهادی و کمک‌رسانی هم‌محله‌ای —
            همه در یک پلتفرم.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 md:gap-6">
          {PILLARS.map((p, i) => (
            <motion.div
              key={p.href}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.45, delay: i * 0.05 }}
            >
              <Link
                href={p.href}
                className="group relative block h-full p-6 md:p-7 card overflow-hidden"
              >
                <div
                  aria-hidden
                  className={`absolute -top-16 -left-16 w-48 h-48 rounded-full bg-gradient-to-br ${p.tint} opacity-50 blur-2xl
                              group-hover:opacity-80 transition-opacity`}
                />
                <div className="relative flex items-start justify-between">
                  <div
                    className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${p.tint}
                                flex items-center justify-center shadow-soft`}
                  >
                    <p.Icon className="w-7 h-7" />
                  </div>
                  <span className={`h-2 w-2 rounded-full ${p.pill}`} />
                </div>
                <h3 className="relative mt-5 text-xl font-bold text-ink-900 group-hover:text-brand-700 transition-colors">
                  {p.title}
                </h3>
                <p className="relative mt-2 text-[14.5px] leading-7 text-ink-600">
                  {p.desc}
                </p>
                <div className="relative mt-5 inline-flex items-center gap-1.5 text-brand-600 font-semibold text-sm">
                  مشاهده بخش
                  <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
