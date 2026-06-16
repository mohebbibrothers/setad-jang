import type { MetadataRoute } from 'next';
import { siteConfig } from '@/lib/site';

/**
 * Dynamic sitemap. Static routes are listed here; per-resource sitemaps
 * (campaigns, courses, content, criminals, listings, reports) will be
 * appended in subsequent steps using server-side data fetching.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteConfig.url.replace(/\/+$/, '');
  const now = new Date();

  const staticRoutes = [
    { path: '/',                priority: 1.0, changeFrequency: 'daily' as const },
    { path: '/madadkar',        priority: 0.95, changeFrequency: 'daily' as const },
    { path: '/lms',             priority: 0.9, changeFrequency: 'daily' as const },
    { path: '/kindness-wall',   priority: 0.9, changeFrequency: 'hourly' as const },
    { path: '/r4j',             priority: 0.85, changeFrequency: 'weekly' as const },
    { path: '/tabyin',          priority: 0.85, changeFrequency: 'daily' as const },
    { path: '/public-reports',  priority: 0.8, changeFrequency: 'weekly' as const },
    { path: '/support',         priority: 0.6, changeFrequency: 'monthly' as const },
    { path: '/about',           priority: 0.7, changeFrequency: 'monthly' as const },
    { path: '/contact',         priority: 0.6, changeFrequency: 'monthly' as const },
    { path: '/auth/login',      priority: 0.4, changeFrequency: 'yearly' as const },
    { path: '/auth/signup',     priority: 0.4, changeFrequency: 'yearly' as const },
    { path: '/faq',             priority: 0.5, changeFrequency: 'monthly' as const },
    { path: '/privacy',         priority: 0.3, changeFrequency: 'yearly' as const },
    { path: '/terms',           priority: 0.3, changeFrequency: 'yearly' as const },
  ];

  return staticRoutes.map((r) => ({
    url: `${base}${r.path}`,
    lastModified: now,
    changeFrequency: r.changeFrequency,
    priority: r.priority,
  }));
}
