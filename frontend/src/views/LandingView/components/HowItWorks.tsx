import { HOW_IT_WORKS_HEADING, HOW_IT_WORKS_ID, HOW_IT_WORKS_STEPS } from "../constants";
import { HowItWorksStep } from "./HowItWorksStep";

/** The explainer: three steps from logging a win to exporting a targeted resume. */
export function HowItWorks() {
  return (
    <section id={HOW_IT_WORKS_ID} className="flex flex-col gap-8">
      <h2 className="text-2xl font-semibold tracking-tight">{HOW_IT_WORKS_HEADING}</h2>
      <ol className="grid gap-4 sm:grid-cols-3">
        {HOW_IT_WORKS_STEPS.map((step, index) => (
          <HowItWorksStep key={step.title} step={step} index={index} />
        ))}
      </ol>
    </section>
  );
}
