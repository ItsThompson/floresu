import { HERO_HEADLINE, WORDMARK } from "../constants";

/** Slim brand footer: the wordmark and the tagline. No links, so nothing 404s. */
export function LandingFooter() {
  return (
    <footer className="reading-width text-muted-foreground flex w-full flex-col gap-2 border-t px-6 py-8 text-sm sm:flex-row sm:items-baseline sm:justify-between">
      <span className="text-foreground font-serif text-xl font-medium lowercase tracking-tight">
        {WORDMARK}
      </span>
      <span>{HERO_HEADLINE}</span>
    </footer>
  );
}
