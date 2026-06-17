'use client';

import { useState } from 'react';
import { Send } from 'lucide-react';

/**
 * Newsletter bar — matches designer mockup:
 *  - thin brand-coloured notch at top center
 *  - solid teal outer pill with white inner input pill
 *  - gold "ارسال" button
 */
export function NewsletterBar() {
  const [email, setEmail] = useState('');
  const [done, setDone] = useState(false);

  return (
    <section className="py-8 md:py-14 bg-white">
      <div className="container-edge">
        <div className="relative max-w-3xl mx-auto pt-8">
          {/* Decorative arched notch on top */}
          <div
            aria-hidden="true"
            className="absolute top-0 left-1/2 -translate-x-1/2 w-10 h-6
                       bg-brand-500 rounded-t-full shadow-[0_-2px_8px_rgba(0,0,0,0.05)]"
          />
          <form
            onSubmit={(e) => { e.preventDefault(); if (email) { setDone(true); setEmail(''); } }}
            className="relative bg-brand-500 rounded-full shadow-soft flex items-center gap-2 p-2"
            aria-label="فرم خبرنامه"
          >
            <label
              htmlFor="newsletter-email"
              className="px-4 md:px-6 text-white font-bold text-sm md:text-base whitespace-nowrap"
            >
              عضویت در خبرنامه
            </label>
            <div className="flex-1 bg-white rounded-full h-11 flex items-center px-4">
              <input
                id="newsletter-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="آدرس ایمیل…"
                aria-label="آدرس ایمیل"
                dir="rtl"
                className="flex-1 h-full bg-transparent outline-none text-sm
                           text-ink-900 placeholder:text-ink-400 text-right"
              />
            </div>
            <button
              type="submit"
              className="inline-flex items-center justify-center gap-1.5 h-11 px-5 md:px-7 rounded-full
                         bg-gold-500 hover:bg-gold-600 text-ink-900 text-sm font-bold transition-colors shrink-0"
            >
              <Send className="w-4 h-4" strokeWidth={2.2} />
              ارسال
            </button>
          </form>
          {done && (
            <p className="text-center mt-3 text-sm text-brand-700">
              ✓ ثبت‌نام شما در خبرنامه با موفقیت انجام شد.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
