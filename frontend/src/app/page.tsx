import type { Metadata } from 'next';
import { Hero } from '@/components/home/Hero';
import { Pillars } from '@/components/home/Pillars';
import { CampaignsTeaser } from '@/components/home/CampaignsTeaser';
import { JusticeRail } from '@/components/home/JusticeRail';
import { LearningShowcase } from '@/components/home/LearningShowcase';
import { KindnessWall } from '@/components/home/KindnessWall';
import { TabyinGrid } from '@/components/home/TabyinGrid';
import { ReportCTA } from '@/components/home/ReportCTA';
import { Stats } from '@/components/home/Stats';
import { FAQ } from '@/components/home/FAQ';
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

export default function HomePage() {
  return (
    <>
      <Hero />
      <Pillars />
      <CampaignsTeaser />
      <JusticeRail />
      <LearningShowcase />
      <Stats />
      <TabyinGrid />
      <KindnessWall />
      <ReportCTA />
      <FAQ />
    </>
  );
}
