import { Instagram, Twitter, Linkedin } from 'lucide-react';
import Link from 'next/link';

/**
 * Top thin bar shown above the main header in the designer mockup.
 * - Left: social icons
 * - Right: partner / sub-org quick links
 * Hidden on mobile to keep header clean.
 */
export function TopBar() {
  return (
    <div className="hidden md:block bg-brand-600 text-white text-[12.5px]">
      <div className="container-edge h-9 flex items-center gap-4">
        {/* Partner links — visually RIGHT in RTL (matches designer mockup) */}
        <div className="flex items-center gap-4">
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">بنیاد علوی</Link>
          <span className="opacity-30">•</span>
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">زرم‌گیش</Link>
          <span className="opacity-30">•</span>
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">جهادگرا</Link>
          <span className="opacity-30">•</span>
          <Link href="#" className="opacity-90 hover:opacity-100 transition-opacity">حرکت‌های مردمی و جهادی</Link>
        </div>

        {/* Social icons — visually LEFT in RTL */}
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
