/**
 * The calm field shape: border, fill, ink, placeholder, the bloom focus ring, and
 * the invalid-border pairing.
 *
 * It is defined once here because more than one control has to look identical:
 * `FormInputField` for a single-line value, `FormTextareaField` for a multi-line
 * one, and native controls that neither can wrap (a `<select>`, or a dense field
 * whose name comes from `aria-label` rather than a visible label). Import it
 * instead of restating the classes: `aria-invalid:border-destructive` is the part
 * a restatement loses first, and a field that quietly stops marking itself
 * invalid is not something the build can catch.
 *
 * It carries no height, width, or padding, so each caller sets its own density.
 */
export const FIELD_SHAPE_CLASS =
  "border-input bg-card text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive rounded-md border text-sm outline-none focus-visible:ring-[3px]";

/** The caption register every field label renders in. */
export const FIELD_LABEL_CLASS = "text-foreground caption";
