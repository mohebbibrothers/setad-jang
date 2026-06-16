import { cn } from '@/lib/utils';

type LogoProps = {
  className?: string;
  /** show full lockup with wordmark next to glyph */
  withWordmark?: boolean;
  /** force monochrome variant on dark backgrounds */
  variant?: 'color' | 'light' | 'dark';
  size?: number;
  ariaLabel?: string;
};

/**
 * Inline SVG re-creation of the "بعثت مردم" logo (climber + Iranian flag on mountain).
 * Crisp at any size, no network request, instant first paint.
 */
export function Logo({
  className,
  withWordmark = true,
  variant = 'color',
  size = 44,
  ariaLabel = 'بعثت مردم',
}: LogoProps) {
  const teal  = variant === 'light' ? '#FFFFFF' : '#1F8A7A';
  const tealDark = variant === 'light' ? '#FFFFFF' : '#155F55';
  const sun   = variant === 'light' ? 'rgba(255,255,255,0.85)' : '#F4B23B';
  const text  = variant === 'light' ? '#FFFFFF' : '#155F55';

  return (
    <div className={cn('flex items-center gap-3 select-none', className)} aria-label={ariaLabel}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 96 96"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-hidden="true"
        className="shrink-0"
      >
        {/* Sun */}
        <circle cx="60" cy="38" r="22" fill={sun} />
        {/* Sun rays */}
        <g stroke={sun} strokeWidth="3" strokeLinecap="round" opacity="0.9">
          <line x1="60" y1="6" x2="60" y2="12" />
          <line x1="86" y1="14" x2="82" y2="18" />
          <line x1="92" y1="38" x2="86" y2="38" />
          <line x1="86" y1="62" x2="82" y2="58" />
          <line x1="34" y1="14" x2="38" y2="18" />
          <line x1="28" y1="38" x2="34" y2="38" />
        </g>
        {/* Mountain */}
        <path
          d="M6 84 L34 50 L46 64 L60 44 L92 84 Z"
          fill={teal}
        />
        {/* Mountain shadow */}
        <path
          d="M60 44 L92 84 L70 84 Z"
          fill={tealDark}
          opacity="0.75"
        />
        {/* Climbers (stylized stick figures) */}
        <g fill={teal}>
          <circle cx="20" cy="70" r="3" />
          <rect x="18" y="73" width="4" height="7" rx="1.5" />
          <circle cx="30" cy="64" r="3" />
          <rect x="28" y="67" width="4" height="8" rx="1.5" />
          <circle cx="42" cy="58" r="3" />
          <rect x="40" y="61" width="4" height="9" rx="1.5" />
        </g>
        {/* Leader holding flag */}
        <g fill={tealDark}>
          <circle cx="56" cy="48" r="3.5" />
          <rect x="54" y="51" width="4" height="10" rx="1.5" />
        </g>
        {/* Flag pole + flag */}
        <line x1="62" y1="20" x2="62" y2="52" stroke={tealDark} strokeWidth="2" strokeLinecap="round" />
        <path d="M62 22 L84 24 L78 32 L84 40 L62 38 Z" fill={teal} />
        {/* Flag emblem (simplified) */}
        <circle cx="73" cy="31" r="2.4" fill="#FFFFFF" opacity="0.92" />
      </svg>

      {withWordmark && (
        <div className="flex flex-col leading-none" style={{ color: text }}>
          <span className="text-[20px] font-extrabold tracking-tight">بعثت</span>
          <span className="text-[20px] font-extrabold tracking-tight -mt-0.5">مردم</span>
        </div>
      )}
    </div>
  );
}
