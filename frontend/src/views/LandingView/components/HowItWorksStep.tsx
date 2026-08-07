import type { HowItWorksStepData } from "../types";

interface HowItWorksStepProps {
  step: HowItWorksStepData;
  index: number;
}

/** One step: an icon, its two-digit position, a title, and a single line. */
export function HowItWorksStep({ step, index }: HowItWorksStepProps) {
  const { icon: Icon, title, body } = step;

  return (
    <li className="bg-card text-card-foreground flex flex-col gap-3 rounded-lg border p-6">
      <div className="flex items-center gap-3">
        <span className="bg-accent text-accent-foreground flex size-9 items-center justify-center rounded-full">
          <Icon aria-hidden className="size-4" />
        </span>
        <span className="mono-meta text-muted-foreground">
          {String(index + 1).padStart(2, "0")}
        </span>
      </div>
      <h3 className="font-semibold">{title}</h3>
      <p className="text-muted-foreground text-sm">{body}</p>
    </li>
  );
}
