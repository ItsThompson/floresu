import { VALUE_HEADLINE, VALUE_SUPPORT } from "../constants";

/**
 * The showcase: the page's one loud block. Its text is espresso because light
 * text on the bright bloom fails AA contrast, and the fill carries a headline
 * only: reading copy on bloom is the thing this block must never become.
 */
export function ValueBand() {
  return (
    <section className="grid gap-8 lg:grid-cols-2 lg:items-center">
      <h2 className="bg-bloom text-espresso rounded-xl px-8 py-10 font-serif text-3xl leading-tight font-medium">
        {VALUE_HEADLINE}
      </h2>
      <p className="text-foreground text-lg">{VALUE_SUPPORT}</p>
    </section>
  );
}
