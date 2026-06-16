'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { Trophy, ArrowLeft, ShieldAlert } from 'lucide-react';

type Criminal = {
  slug: string;
  name: string;
  role: string;
  bounty: string;
};

const SAMPLE: Criminal[] = [
  { slug: 'salman-rushdie', name: 'سلمان رشدی', role: 'توهین به مقدسات', bounty: '۳ میلیون دلار' },
  { slug: 'reza-pahlavi',   name: 'رضا پهلوی',  role: 'خیانت به ملت',  bounty: 'تحت بررسی' },
  { slug: 'yair-lapid',     name: 'یائیر لاپید', role: 'جنایت جنگی',   bounty: '۵ میلیون دلار' },
];

export function JusticeRail() {
  return (
    <section className="section-y bg-white">
      <div className="container-edge">
        <div className="text-center max-w-2xl mx-auto mb-10">
          <span className="eyebrow"><ShieldAlert className="w-4 h-4" /> جایزه عدالت</span>
          <h2 className="mt-4 text-3xl md:text-4xl font-extrabold text-ink-900">
            عدالت، با مشارکت مردم
          </h2>
          <p className="mt-3 text-ink-600 leading-8">
            بانک اطلاعاتی جنایتکاران و سامانه‌ای برای ثبت اطلاعات منجر به اجرای عدالت.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {SAMPLE.map((p, i) => (
            <motion.div
              key={p.slug}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, delay: i * 0.07 }}
              className="card group overflow-hidden"
            >
              <Link href={`/r4j/${p.slug}`} className="block">
                <div className="relative aspect-[4/5] bg-gradient-to-br from-ink-800 to-ink-900 overflow-hidden">
                  <div className="absolute inset-0 bg-grid-pattern opacity-20" />
                  {/* Silhouette placeholder */}
                  <svg viewBox="0 0 100 120" className="absolute inset-x-0 bottom-0 w-full text-ink-700">
                    <circle cx="50" cy="38" r="20" fill="currentColor" />
                    <path d="M10 120 Q10 70 50 70 Q90 70 90 120 Z" fill="currentColor" />
                  </svg>
                  <span className="absolute top-3 right-3 text-[11px] font-semibold px-2.5 py-1 rounded-full
                                   bg-danger text-white">
                    تحت تعقیب
                  </span>
                </div>
                <div className="p-5">
                  <h3 className="font-bold text-ink-900 group-hover:text-brand-700 transition-colors">
                    {p.name}
                  </h3>
                  <p className="mt-1 text-sm text-ink-500">{p.role}</p>
                  <div className="mt-4 flex items-center justify-between">
                    <span className="text-xs text-ink-500">جایزه</span>
                    <span className="font-bold text-accent-600 text-sm">{p.bounty}</span>
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}

          {/* Trophy CTA card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.45, delay: 0.3 }}
            className="card relative overflow-hidden bg-gradient-to-br from-accent-400 to-accent-600 text-ink-900"
          >
            <div className="absolute inset-0 bg-grid-pattern opacity-20" />
            <div className="relative p-6 flex flex-col h-full justify-between min-h-[280px]">
              <div className="w-14 h-14 rounded-2xl bg-white/90 flex items-center justify-center shadow-soft">
                <Trophy className="w-7 h-7 text-accent-600" />
              </div>
              <div>
                <h3 className="text-xl font-extrabold">جایزه عدالت</h3>
                <p className="mt-2 text-sm leading-7">
                  مشاهده فهرست کامل و ثبت اطلاعات منجر به دستگیری مجرمان.
                </p>
                <Link href="/r4j" className="mt-4 inline-flex items-center gap-1.5 font-bold text-ink-900">
                  مشاهده همه <ArrowLeft className="w-4 h-4" />
                </Link>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
