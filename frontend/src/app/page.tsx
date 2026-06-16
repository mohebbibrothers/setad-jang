import type { Metadata } from 'next';
import { Hero } from '@/components/home/Hero';
import { ActivitiesPanel } from '@/components/home/ActivitiesPanel';
import { WarFundSection } from '@/components/home/WarFundSection';
import { JusticeSection } from '@/components/home/JusticeSection';
import { EducationSection } from '@/components/home/EducationSection';
import { KindnessSection } from '@/components/home/KindnessSection';
import { TabyinSection } from '@/components/home/TabyinSection';
import { PublicReportSection } from '@/components/home/PublicReportSection';
import { NewsletterBar } from '@/components/home/NewsletterBar';
import {
  loadCampaigns,
  loadCriminals,
  loadCourses,
  loadKindnessListings,
  loadTabyinItems,
} from '@/lib/home-data';
import { siteConfig } from '@/lib/site';

export const metadata: Metadata = {
  title: `${siteConfig.name} — ${siteConfig.slogan}`,
  description: siteConfig.description,
  alternates: { canonical: '/' },
  openGraph: {
    url: '/',
    title: `${siteConfig.name} — ${siteConfig.slogan}`,
    description: siteConfig.description,
  },
};

// SSR with backend revalidation every 5 minutes
export const revalidate = 300;

export default async function HomePage() {
  const [campaigns, criminals, courses, kindness, tabyin] = await Promise.all([
    loadCampaigns(),
    loadCriminals(),
    loadCourses(),
    loadKindnessListings(),
    loadTabyinItems(),
  ]);

  return (
    <>
      <Hero />
      <ActivitiesPanel />
      <WarFundSection campaigns={campaigns} />
      <JusticeSection criminals={criminals} />
      <EducationSection courses={courses} />
      <KindnessSection listings={kindness} />
      <TabyinSection items={tabyin} />
      <PublicReportSection />
      <NewsletterBar />
    </>
  );
}
