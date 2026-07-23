/**
 * The variant form's controlled values: a flat, form-representation shape. Links
 * are held as one "Label | url" pair per line (`linksText`), not the typed
 * `VariantLink[]` the API carries; the submit build derives the write body from
 * these values.
 */
export interface VariantFormValues {
  label: string;
  fullName: string;
  email: string;
  phone: string;
  location: string;
  linksText: string;
  isDefault: boolean;
}
