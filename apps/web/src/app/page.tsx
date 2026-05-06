import { Hero }            from "@/components/sections/hero";
import { PillarsSection }  from "@/components/sections/pillars-section";
import { JourneySection }  from "@/components/sections/journey-section";
import { FeaturesSection } from "@/components/sections/features-section";
import { PulseSection }    from "@/components/sections/pulse-section";
import { StorySection }    from "@/components/sections/story-section";
import { AudienceSection } from "@/components/sections/audience-section";
import { PricingSection }  from "@/components/sections/pricing-section";
import { FinalCta }        from "@/components/sections/final-cta";

export default function HomePage() {
  return (
    <main>
      <Hero />
      <PillarsSection />
      <JourneySection />
      <FeaturesSection />
      <PulseSection />
      <StorySection />
      <AudienceSection />
      <PricingSection />
      <FinalCta />
    </main>
  );
}