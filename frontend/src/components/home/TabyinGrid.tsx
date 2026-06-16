'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { Megaphone, ArrowLeft, Eye, Heart } from 'lucide-react';

type Card = { id: string; title: string; tag: string; tone: string };

const ITEMS: Card[] = [
  { id: 'a', title: 'افسانه راست پنداشتن چپ', tag: 'تحلیل',  tone: 'from-emerald-500 to-emerald-800' },
  { id: 'b', title: 'روایت‌سازی غربی از غزه',   tag: 'رسانه', tone: 'from-rose-500 to-rose-800' },
  { id: 'c', title: 'حقایق پشت تحریم‌ها',      tag: 'اقتصاد', tone: 'from-amber-500 to-amber-700' },
  { id: 'd', title: 'چرا هویت ملی مهم است؟',    tag: 'فرهنگ', tone: 'from-indigo-500 to-indigo-800' },
  { id: 'e', title: 'جنگ نرم در فضای مجازی',     tag: 'سواد رسانه', tone: 'from-brand-500 to-brand-800' },
  { id: 'f', title: 'مقایسه نرخ رشد ایران و منطقه', tag: 'اینفوگرافیک', tone: 'from-violet-500 to-violet-800' },
];

export function TabyinGrid() {
  return (
    <section className="section-y bg-surface-muted">
      <div className="container-edge">
        <div className="flex items-end justify-between gap-6 mb-10">
          <div>
            <span className="eyebrow"><Megaphone className="w-4 h-4" /> جهاد تبیین</span>
            <h2 className="mt-4 text-3xl md:text-4xl font-extrabold text-ink-900">
              تازه‌ترین محتوای روشنگرانه
            </h2>
            <p className="mt-3 text-ink-600 max-w-xl leading-8">
              مجموعه‌ای از تحلیل‌ها، اینفوگرافیک‌ها و کلیپ‌های کوتاه برای روایت درست.
            </p>
          </div>
          <Link href="/tabyin" className="hidden md:inline-flex btn-outline btn-md">
            مشاهده بانک محتوا <ArrowLeft className="w-4 h-4" />
          </Link>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
          {ITEMS.map((c, i) => (
            <motion.div
              key={c.id}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.04 }}
            >
              <Link
                href={`/tabyin/${c.id}`}
                className={`group relative block aspect-[3/4] rounded-2xl overflow-hidden shadow-soft
                            bg-gradient-to-br ${c.tone}`}
              >
                <div className="absolute inset-0 bg-grid-pattern opacity-25" />
                <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/15 to-transparent" />
                <span className="absolute top-3 right-3 text-[10px] font-bold px-2 py-0.5 rounded-full bg-white/90 text-ink-900">
                  {c.tag}
                </span>
                <div className="absolute bottom-0 inset-x-0 p-3 text-white">
                  <p className="text-[13px] font-bold leading-6 line-clamp-2">{c.title}</p>
                  <div className="mt-2 flex items-center gap-3 text-[11px] opacity-90">
                    <span className="inline-flex items-center gap-1"><Eye className="w-3 h-3" /> ۱.۲K</span>
                    <span className="inline-flex items-center gap-1"><Heart className="w-3 h-3" /> ۴۸</span>
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
