'use client';

import Link from 'next/link';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="text-center max-w-lg">
        <div className="mx-auto w-20 h-20 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center">
          <AlertTriangle className="w-10 h-10" />
        </div>
        <h1 className="mt-5 text-2xl md:text-3xl font-bold text-ink-900">خطایی رخ داد</h1>
        <p className="mt-3 text-ink-600 leading-8">
          متأسفانه در نمایش این صفحه مشکلی پیش آمده است. لطفاً دوباره تلاش کنید.
        </p>
        {error?.digest && (
          <p className="mt-2 text-xs text-ink-400 ltr">code: {error.digest}</p>
        )}
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button onClick={() => reset()} className="btn-primary btn-md">
            <RefreshCw className="w-4 h-4" /> تلاش دوباره
          </button>
          <Link href="/" className="btn-outline btn-md">
            <Home className="w-4 h-4" /> بازگشت به خانه
          </Link>
        </div>
      </div>
    </section>
  );
}
