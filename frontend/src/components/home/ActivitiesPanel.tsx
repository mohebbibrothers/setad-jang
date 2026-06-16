'use client';

import Image from 'next/image';
import Link from 'next/link';
import { motion } from 'framer-motion';

type Activity = {
  href: string;
  label: string;
  icon: string;          // path under /brand/
  iconAlt: string;
};

/**
 * The 5 main activity icons, mapped to backend apps.
 * Order taken directly from the designer's mockup.
 */
const ACTIVITIES: Activity[] = [
  { href: '/tabyin',        label: 'جهاد تبیین',     icon: '/brand/icon-tabyin.png',  iconAlt: 'جهاد تبیین' },
  { href: '/kindness-wall', label: 'دیوار مهربانی',  icon: '/brand/icon-kindness.png',iconAlt: 'دیوار مهربانی' },
  { href: '/lms',           label: 'قرارگاه آموزشی', icon: '/brand/icon-lms.png',     iconAlt: 'قرارگاه آموزشی' },
  { href: '/r4j',           label: 'جایزه برای عدالت',icon: '/brand/icon-r4j.png',    iconAlt: 'جایزه برای عدالت' },
  { href: '/madadkar',      label: 'پشتیبانی مالی جنگ', icon: '/brand/icon-warfund.png', iconAlt: 'پشتیبانی مالی جنگ' },
];

/**
 * Curved teal panel with 5 white pill cards.
 * Mirrors the designer's signature "اهم فعالیت‌ها" hero panel.
 */
export function ActivitiesPanel() {
  return (
    <section className="relative pt-10 md:pt-14 pb-16 md:pb-20" aria-labelledby="activities-title">
      <div className="container-edge">
        {/* Curved teal panel */}
        <div className="relative rounded-[2rem] md:rounded-[2.5rem] bg-brand-500 text-white overflow-hidden">
          {/* Top notch with double chevron — matches Asset 20 */}
          <div
            aria-hidden="true"
            className="absolute top-0 left-1/2 -translate-x-1/2 w-24 h-6 bg-white rounded-b-full
                       flex items-end justify-center pb-1"
          >
            <svg viewBox="0 0 20 14" className="w-5 h-3 text-brand-500" fill="none">
              <path d="M2 2l8 6 8-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 7l8 6 8-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity=".6"/>
            </svg>
          </div>

          {/* Plus pattern background (subtle) */}
          <div
            aria-hidden="true"
            className="absolute inset-0 opacity-[0.08] pointer-events-none"
            style={{
              backgroundImage:
                "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.7) 1px, transparent 1px)",
              backgroundSize: '24px 24px',
            }}
          />

          <div className="relative px-5 sm:px-8 md:px-12 pt-12 md:pt-14 pb-10 md:pb-14">
            <motion.h2
              id="activities-title"
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className="text-center text-xl md:text-2xl font-extrabold mb-8 md:mb-10"
            >
              اهم فعالیت‌ها
            </motion.h2>

            {/* 5 white cards in a single row, scrollable on mobile */}
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 md:gap-4 lg:gap-6">
              {ACTIVITIES.map((a, i) => (
                <motion.div
                  key={a.href}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: i * 0.06 }}
                >
                  <Link
                    href={a.href}
                    className="group block rounded-2xl bg-white text-ink-800 p-4 md:p-5
                               shadow-[0_8px_24px_-12px_rgba(0,0,0,0.25)]
                               hover:-translate-y-1 hover:shadow-[0_16px_36px_-12px_rgba(0,0,0,0.3)]
                               transition-all duration-300 h-full flex flex-col items-center text-center"
                  >
                    <div className="w-16 h-16 md:w-[72px] md:h-[72px] flex items-center justify-center
                                    rounded-xl bg-white group-hover:scale-110 transition-transform">
                      <Image src={a.icon} alt={a.iconAlt} width={72} height={72} className="w-full h-full object-contain" />
                    </div>
                    <p className="mt-3 md:mt-4 text-[13px] md:text-[14.5px] font-semibold text-ink-700 leading-tight">
                      {a.label}
                    </p>
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
