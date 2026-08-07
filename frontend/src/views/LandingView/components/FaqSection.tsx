import { FAQ_HEADING, FAQ_ITEMS } from "../constants";
import { FaqItem } from "./FaqItem";

/** The questions a visitor asks before signing up, answered plainly. */
export function FaqSection() {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-2xl font-semibold tracking-tight">{FAQ_HEADING}</h2>
      <div className="flex flex-col">
        {FAQ_ITEMS.map((item) => (
          <FaqItem key={item.question} item={item} />
        ))}
      </div>
    </section>
  );
}
