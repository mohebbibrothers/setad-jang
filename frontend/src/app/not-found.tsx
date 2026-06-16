import Link from 'next/link';
import { Home, Search } from 'lucide-react';

export const metadata = { title: 'صفحه یافت نشد' };

export default function NotFound() {
  return (
    <section className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        <p className="text-[120px] font-extrabold leading-none text-gradient-brand">۴۰۴</p>
        <h1 className="text-2xl md:text-3xl font-bold text-ink-900 mt-2">صفحه‌ای که دنبالش بودید پیدا نشد</h1>
        <p className="mt-3 text-ink-600 leading-8">
          ممکن است آدرس را اشتباه وارد کرده باشید یا این صفحه جابه‌جا شده باشد.
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <Link href="/" className="btn-primary btn-md">
            <Home className="w-4 h-4" /> بازگشت به خانه
          </Link>
          <Link href="/search" className="btn-outline btn-md">
            <Search className="w-4 h-4" /> جست‌وجو در سایت
          </Link>
        </div>
      </div>
    </section>
  );
}
