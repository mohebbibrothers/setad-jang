import { Instagram, Twitter, Linkedin } from 'lucide-react';
import Link from 'next/link';

/**
 * Top thin teal bar — partner links on the right (RTL), social on the left.
 * No dot separators (matches designer mockup); links use generous gap instead.
 */
export function TopBar() {
  return (
    <div className="hidden md:block bg-brand-600 text-white text-[12.5px]">
      <div className="container-edge h-9 flex items-center gap-4">
        {/* Partner links — visually RIGHT in RTL */}
        <div className="flex items-center gap-8">
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">بنیاد علوی</Link>
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">زرفام کیش</Link>
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">جهادآرا</Link>
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">حرکت‌های مردمی و جهادی</Link>
        </div>

        {/* Social icons — visually LEFT */}
        <div className="mr-auto flex items-center gap-3">
          <Link href="#" aria-label="اینستاگرام" className="opacity-90 hover:opacity-100 transition-opacity">
            <Instagram className="w-4 h-4" />
          </Link>
          <Link href="#" aria-label="توییتر" className="opacity-90 hover:opacity-100 transition-opacity">
            <Twitter className="w-4 h-4" />
          </Link>
          <Link href="#" aria-label="لینکدین" className="opacity-90 hover:opacity-100 transition-opacity">
            <Linkedin className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}
