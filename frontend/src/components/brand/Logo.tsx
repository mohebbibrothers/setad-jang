import Image from 'next/image';
import { cn } from '@/lib/utils';

type LogoProps = {
  className?: string;
  /** Pixel width of the logo image (auto height). */
  width?: number;
  priority?: boolean;
  ariaLabel?: string;
  /** Use the transparent PNG variant (e.g. for footer on coloured bg). */
  transparent?: boolean;
};

/**
 * Brand logo as delivered by the graphic designer.
 * Uses the official "بعثت مردم" lockup (climber + Iranian flag + sun).
 * Two variants:
 *   - JPG with white background (default, used in header on white)
 *   - PNG with transparent background (used in footer)
 */
export function Logo({
  className,
  width = 132,
  priority = false,
  ariaLabel = 'بعثت مردم',
  transparent = false,
}: LogoProps) {
  const src = transparent ? '/brand/logo-transparent.png' : '/brand/logo-full.jpg';
  // Native aspect ratios: jpg ~ 1026x491, png ~ 185x70 (≈ 2.64:1)
  const ratio = transparent ? 70 / 185 : 491 / 1026;
  return (
    <Image
      src={src}
      alt={ariaLabel}
      width={width}
      height={Math.round(width * ratio)}
      priority={priority}
      className={cn('h-auto select-none', className)}
      sizes="(max-width: 640px) 110px, 140px"
    />
  );
}
