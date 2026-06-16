import Link from 'next/link';
import { Mail, Send, MapPin, ShieldCheck } from 'lucide-react';
import { Logo } from '@/components/brand/Logo';
import { footerNav } from '@/lib/nav';
import { siteConfig } from '@/lib/site';

export function Footer() {
  return (
    <footer className="relative mt-20 text-white bg-gradient-to-b from-brand-700 to-brand-900 overflow-hidden">
      {/* Decorative background pattern */}
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.07] bg-grid-pattern pointer-events-none"
      />
      <div
        aria-hidden="true"
        className="absolute -top-32 -left-32 w-[480px] h-[480px] rounded-full
                   bg-accent-500/20 blur-3xl pointer-events-none"
      />

      <div className="relative container-edge pt-16 pb-8">
        {/* Newsletter strip */}
        <div className="rounded-3xl bg-white/10 backdrop-blur-sm border border-white/15 p-6 md:p-8
                        flex flex-col md:flex-row items-center gap-6 mb-14">
          <div className="flex-1 text-center md:text-right">
            <h3 className="text-xl md:text-2xl font-bold mb-1">
              عضو خبرنامه بعثت مردم شوید
            </h3>
            <p className="text-white/75 text-sm md:text-base">
              تازه‌ترین کمپین‌ها، گزارش‌ها و آموزش‌ها را اول از همه دریافت کنید.
            </p>
          </div>
          <form className="w-full md:w-auto flex gap-2" aria-label="فرم خبرنامه">
            <input
              type="email"
              required
              placeholder="ایمیل شما"
              aria-label="ایمیل"
              className="flex-1 md:w-72 h-12 px-4 rounded-xl bg-white/90 text-ink-900
                         placeholder:text-ink-400 focus:bg-white focus:outline-none"
            />
            <button type="submit" className="btn-accent btn-md">
              <Send className="w-4 h-4 -rotate-45" />
              عضویت
            </button>
          </form>
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-8 lg:gap-10">
          <div className="lg:col-span-4">
            <Logo size={48} variant="light" />
            <p className="mt-5 text-white/75 text-[15px] leading-7 max-w-md">
              {siteConfig.description}
            </p>
            <div className="mt-6 space-y-3 text-sm text-white/80">
              {siteConfig.contact.email && (
                <a href={`mailto:${siteConfig.contact.email}`} className="flex items-center gap-2 hover:text-white">
                  <Mail className="w-4 h-4" /> {siteConfig.contact.email}
                </a>
              )}
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4" /> جمهوری اسلامی ایران
              </div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-accent-300" />
                درگاه پرداخت امن مردمی
              </div>
            </div>
          </div>

          {footerNav.map((group) => (
            <nav key={group.label} className="lg:col-span-2" aria-label={group.label}>
              <h4 className="font-bold text-white mb-4">{group.label}</h4>
              <ul className="space-y-2.5">
                {group.items.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="text-white/75 hover:text-white transition-colors text-[14px]"
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}

          <div className="lg:col-span-2">
            <h4 className="font-bold text-white mb-4">نمادها</h4>
            <div className="flex gap-2">
              <div className="w-20 h-24 rounded-xl bg-white/10 border border-white/15
                              flex items-center justify-center text-[10px] text-white/60 text-center px-1">
                نماد اعتماد الکترونیکی
              </div>
              <div className="w-20 h-24 rounded-xl bg-white/10 border border-white/15
                              flex items-center justify-center text-[10px] text-white/60 text-center px-1">
                ساماندهی رسانه
              </div>
            </div>
          </div>
        </div>

        <div className="mt-12 pt-6 border-t border-white/10 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-white/65">
          <p>
            © {new Date().getFullYear()} {siteConfig.name}. تمامی حقوق محفوظ است.
          </p>
          <p>
            طراحی و توسعه با ❤️ برای مردم ایران
          </p>
        </div>
      </div>
    </footer>
  );
}
