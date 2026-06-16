'use client';

import { useState } from 'react';
import { Send } from 'lucide-react';

/**
 * Designer's pill-shaped newsletter strip with floating arrow notch above.
 * Sits between report form and footer.
 */
export function NewsletterBar() {
  const [email, setEmail] = useState('');
  const [done, setDone] = useState(false);

  return (
    <section className="py-10 md:py-14 bg-white">
      <div className="container-edge">
        <div className="relative max-w-3xl mx-auto">
          {/* Top arrow notch */}
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 w-10 h-6 bg-brand-500
                          rounded-t-full" aria-hidden="true" />
          <form
            onSubmit={(e) => { e.preventDefault(); if (email) { setDone(true); setEmail(''); } }}
            className="relative bg-white rounded-full border-2 border-brand-500 shadow-soft
                       flex items-center pr-2 pl-2 sm:pr-6 py-2"
            aria-label="فرم خبرنامه"
          >
            <label htmlFor="newsletter" className="font-bold text-brand-600 text-sm md:text-base px-2 md:px-3 whitespace-nowrap">
              عضویت در خبرنامه
            </label>
            <input
              id="newsletter"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="آدرس ایمیل…"
              aria-label="آدرس ایمیل"
              className="flex-1 mx-1 md:mx-3 h-10 bg-transparent outline-none text-sm
                         text-ink-900 placeholder:text-ink-400"
            />
            <button
              type="submit"
              className="inline-flex items-center justify-center gap-1.5 h-10 px-4 md:px-6 rounded-full
                         bg-gold-500 hover:bg-gold-600 text-ink-900 text-sm font-bold transition-colors"
            >
              <Send className="w-4 h-4 -rotate-45" />
              ارسال
            </button>
          </form>
          {done && (
            <p className="text-center mt-3 text-sm text-brand-700">
              ✅ ثبت‌نام شما در خبرنامه با موفقیت انجام شد.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
