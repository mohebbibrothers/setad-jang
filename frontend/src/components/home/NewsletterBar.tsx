'use client';

import { useState } from 'react';
import { Send } from 'lucide-react';

/**
 * Newsletter pill that nests inside the footer's top notch.
 *  - Solid teal outer pill
 *  - White inner input pill
 *  - Gold "ارسال" button
 *  - Used *inside* <Footer />; does not render its own section padding.
 */
export function NewsletterBar() {
  const [email, setEmail] = useState('');
  const [done, setDone] = useState(false);

  return (
    <>
      <form
        onSubmit={(e) => { e.preventDefault(); if (email) { setDone(true); setEmail(''); } }}
        className="relative bg-brand-500 rounded-full shadow-[0_8px_32px_-8px_rgba(11,53,48,0.2)]
                   flex items-center gap-1.5 p-1.5 md:p-[7px]"
        aria-label="فرم خبرنامه"
      >
        <label
          htmlFor="newsletter-email"
          className="px-3 sm:px-4 md:px-6 text-white font-bold text-[13.5px] sm:text-[14.5px] md:text-base whitespace-nowrap"
        >
          عضویت در خبرنامه
        </label>
        <div className="flex-1 bg-white rounded-full h-[42px] md:h-[46px] flex items-center px-4 min-w-0">
          <input
            id="newsletter-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="آدرس ایمیل…"
            aria-label="آدرس ایمیل"
            dir="rtl"
            className="flex-1 min-w-0 h-full bg-transparent outline-none text-[13px] md:text-sm
                       text-ink-900 placeholder:text-ink-400 text-right"
          />
        </div>
        <button
          type="submit"
          className="inline-flex items-center justify-center gap-1.5 h-[42px] md:h-[46px]
                     px-5 md:px-7 rounded-full
                     bg-gold-500 hover:bg-gold-600 text-ink-900 text-[13px] md:text-sm font-bold
                     transition-colors shrink-0"
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
    </>
  );
}
