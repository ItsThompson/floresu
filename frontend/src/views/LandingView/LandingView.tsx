import { DualModeBand } from "./components/DualModeBand";
import { FaqSection } from "./components/FaqSection";
import { FinalCtaBand } from "./components/FinalCtaBand";
import { HowItWorks } from "./components/HowItWorks";
import { LandingFooter } from "./components/LandingFooter";
import { LandingHeader } from "./components/LandingHeader";
import { LandingHero } from "./components/LandingHero";
import { ValueBand } from "./components/ValueBand";

/**
 * The public page, served to everyone. Chrome-light: a slim header and no app
 * shell. A thin orchestrator over presentational sections, each of which reads
 * its copy from `frontend/src/views/LandingView/constants.ts`; the only logic on
 * the page is the primary action's auth-aware destination, which the button
 * resolves for itself.
 */
export function LandingView() {
  return (
    <div className="bg-background text-foreground flex min-h-svh flex-col">
      <LandingHeader />
      <main className="reading-width flex w-full flex-1 flex-col gap-20 px-6 pt-12 pb-24">
        <LandingHero />
        <HowItWorks />
        <ValueBand />
        <DualModeBand />
        <FaqSection />
        <FinalCtaBand />
      </main>
      <LandingFooter />
    </div>
  );
}
