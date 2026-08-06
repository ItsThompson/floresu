import type { FaqItemData } from "../types";

interface FaqItemProps {
  item: FaqItemData;
}

/** One question with its answer, divided from its neighbour by a hairline. */
export function FaqItem({ item }: FaqItemProps) {
  return (
    <div className="flex flex-col gap-2 border-t py-5">
      <h3 className="font-semibold">{item.question}</h3>
      <p className="text-muted-foreground">{item.answer}</p>
    </div>
  );
}
