'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { HeartHandshake, ArrowLeft, MapPin } from 'lucide-react';

type Item = {
  id: string;
  type: 'need' | 'offer';
  title: string;
  city: string;
  category: string;
};

const ITEMS: Item[] = [
  { id: '1', type: 'need',  title: 'نیازمند یخچال نو/کارکرده برای خانواده ۵ نفره', city: 'تهران',  category: 'لوازم خانگی' },
  { id: '2', type: 'offer', title: 'اهدای کتاب‌های درسی مقطع متوسطه', city: 'مشهد',  category: 'لوازم آموزشی' },
  { id: '3', type: 'need',  title: 'کمک هزینه درمان بیماری خاص', city: 'اصفهان', category: 'سلامت' },
  { id: '4', type: 'offer', title: 'پوشاک نو زمستانی برای کودکان ۳ تا ۸ سال', city: 'شیراز',  category: 'پوشاک' },
  { id: '5', type: 'need',  title: 'استخدام کمک‌فروشنده پاره‌وقت', city: 'تبریز',  category: 'اشتغال' },
  { id: '6', type: 'offer', title: 'مشاوره حقوقی رایگان برای خانواده‌های نیازمند', city: 'قم',     category: 'خدمات' },
];

export function KindnessWall() {
  return (
    <section className="section-y bg-white">
      <div className="container-edge">
        <div className="flex items-end justify-between gap-6 mb-10">
          <div>
            <span className="eyebrow"><HeartHandshake className="w-4 h-4" /> دیوار مهربانی</span>
            <h2 className="mt-4 text-3xl md:text-4xl font-extrabold text-ink-900">
              نیاز و کمک، کنار هم
            </h2>
            <p className="mt-3 text-ink-600 max-w-xl leading-8">
              بدون خرید و فروش، صرفاً برای کمک. هم‌تطبیق هوشمند جغرافیایی برای ارتباط سریع.
            </p>
          </div>
          <Link href="/kindness-wall" className="hidden md:inline-flex btn-outline btn-md">
            ورود به دیوار مهربانی <ArrowLeft className="w-4 h-4" />
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {ITEMS.map((it, i) => (
            <motion.article
              key={it.id}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.04 }}
              className="card p-5 group"
            >
              <div className="flex items-center justify-between mb-3">
                <span
                  className={
                    it.type === 'need'
                      ? 'text-xs font-bold px-2.5 py-1 rounded-full bg-rose-50 text-rose-700'
                      : 'text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700'
                  }
                >
                  {it.type === 'need' ? 'نیازمند کمک' : 'پیشنهاد کمک'}
                </span>
                <span className="text-xs text-ink-500">{it.category}</span>
              </div>
              <Link href={`/kindness-wall/${it.id}`}>
                <h3 className="font-bold text-ink-900 leading-7 group-hover:text-brand-700 transition-colors">
                  {it.title}
                </h3>
              </Link>
              <div className="mt-4 pt-4 border-t border-ink-100 flex items-center justify-between text-sm">
                <span className="inline-flex items-center gap-1.5 text-ink-500">
                  <MapPin className="w-4 h-4" /> {it.city}
                </span>
                <Link href={`/kindness-wall/${it.id}`} className="text-brand-600 font-semibold">
                  مشاهده آگهی
                </Link>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
