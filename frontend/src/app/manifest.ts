import type { MetadataRoute } from 'next';
import { siteConfig } from '@/lib/site';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: siteConfig.name,
    short_name: siteConfig.shortName,
    description: siteConfig.description,
    start_url: '/',
    display: 'standalone',
    background_color: '#FFFFFF',
    theme_color: siteConfig.themeColor,
    orientation: 'portrait',
    dir: 'rtl',
    lang: 'fa-IR',
    icons: [
      { src: '/favicon.svg',       sizes: 'any',    type: 'image/svg+xml', purpose: 'any' },
      { src: '/favicon-192.png',   sizes: '192x192', type: 'image/png',    purpose: 'any maskable' },
      { src: '/favicon-512.png',   sizes: '512x512', type: 'image/png',    purpose: 'any maskable' },
    ],
  };
}
