import Image from 'next/image';
import { cn } from '@/lib/utils';

type LogoProps = {
  className?: string;
  /** Pixel width of the logo image (auto height). */
  width?: number;
  priority?: boolean;
  ariaLabel?: string;
};

/**
 * Brand logo as delivered by the graphic designer.
 * Uses the official "بعثت مردم" lockup (climber + Iranian flag + sun).
 */
export function Logo({
  className,
  width = 132,
  priority = false,
  ariaLabel = 'بعثت مردم',
}: LogoProps) {
  return (
    <Image
      src="/brand/logo-full.jpg"
      alt={ariaLabel}
      width={width}
      height={Math.round((width * 491) / 1026)}
      priority={priority}
      className={cn('h-auto select-none', className)}
      sizes="(max-width: 640px) 110px, 140px"
    />
  );
}
