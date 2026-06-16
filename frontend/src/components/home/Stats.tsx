'use client';

import { motion } from 'framer-motion';
import { Users, HandHeart, GraduationCap, Megaphone } from 'lucide-react';
import { formatPersianNumber } from '@/lib/utils';

const STATS = [
  { Icon: Users,         v: 12480, l: 'کاربر فعال',        tone: 'text-brand-600 bg-brand-50' },
  { Icon: HandHeart,     v: 2410,  l: 'مشارکت مددکاری',    tone: 'text-rose-600 bg-rose-50' },
  { Icon: GraduationCap, v: 6720,  l: 'دانش‌پذیر دوره‌ها',  tone: 'text-violet-600 bg-violet-50' },
  { Icon: Megaphone,     v: 858,   l: 'محتوای تبیینی',     tone: 'text-amber-600 bg-amber-50' },
];

export function Stats() {
  return (
    <section className="py-12 md:py-14 bg-gradient-to-l from-brand-900 to-brand-700 text-white">
      <div className="container-edge">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
          {STATS.map((s, i) => (
            <motion.div
              key={s.l}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.07 }}
              className="flex items-center gap-4"
            >
              <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${s.tone}`}>
                <s.Icon className="w-7 h-7" />
              </div>
              <div>
                <p className="text-3xl font-extrabold tabular-nums">
                  +{formatPersianNumber(s.v)}
                </p>
                <p className="text-sm text-white/75">{s.l}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
