import { Button } from "@/components/ui/button";

import { HERO_HEADLINE, HERO_SECONDARY_LABEL, HERO_SUBHEAD, HOW_IT_WORKS_ID } from "../constants";
import { StartButton } from "./StartButton";

/**
 * Above the fold. The `h1` is the page's single Fraunces display moment; nothing
 * below it uses a display utility. The secondary control is a real anchor to the
 * explainer section rather than a button that scrolls.
 */
export function LandingHero() {
  return (
    <section className="flex flex-col items-start gap-6">
      <h1 className="display-xl max-w-[18ch] text-balance">{HERO_HEADLINE}</h1>
      <p className="text-muted-foreground max-w-[52ch] text-lg">{HERO_SUBHEAD}</p>
      <div className="flex flex-wrap items-center gap-3">
        <StartButton />
        <Button variant="secondary" size="lg" asChild>
          <a href={`#${HOW_IT_WORKS_ID}`}>{HERO_SECONDARY_LABEL}</a>
        </Button>
      </div>
    </section>
  );
}
