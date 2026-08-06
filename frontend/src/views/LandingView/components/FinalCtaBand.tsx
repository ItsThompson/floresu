import { FINAL_CTA_BODY, FINAL_CTA_HEADLINE } from "../constants";
import { StartButton } from "./StartButton";

/**
 * The closing band. The band itself stays calm on card stock so the repeated
 * primary action is the only loud thing here.
 */
export function FinalCtaBand() {
  return (
    <section className="bg-card text-card-foreground flex flex-col items-center gap-5 rounded-xl border px-8 py-12 text-center">
      <h2 className="text-2xl font-semibold tracking-tight">{FINAL_CTA_HEADLINE}</h2>
      <p className="text-muted-foreground max-w-[44ch]">{FINAL_CTA_BODY}</p>
      <StartButton />
    </section>
  );
}
