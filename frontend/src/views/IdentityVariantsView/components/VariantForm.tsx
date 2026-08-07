import { useState, type FormEvent } from "react";

import { FormInputField } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";

import type { IdentityVariantRead, IdentityVariantWrite } from "../hooks/useIdentityVariants";
import type { VariantFormValues } from "../types";
import { linksToText, textToLinks } from "../variantLinks";

interface VariantFormProps {
  /** The variant to edit, or null to create a new one. */
  variant: IdentityVariantRead | null;
  /** Force the default flag on (and locked) when this is the first variant. */
  forceDefault: boolean;
  onSubmit: (write: IdentityVariantWrite) => Promise<boolean>;
  onCancel: () => void;
}

/**
 * Create/edit form for an identity variant: a label, name, optional contact
 * fields, links, and the default flag. Each contact field is optional. When it is
 * the user's first variant the default flag is forced on, matching the backend
 * rule that the first variant is the default. Closes only on a committed write.
 */
export function VariantForm({ variant, forceDefault, onSubmit, onCancel }: VariantFormProps) {
  const [values, setValues] = useState<VariantFormValues>({
    label: variant?.label ?? "",
    fullName: variant?.full_name ?? "",
    email: variant?.contact.email ?? "",
    phone: variant?.contact.phone ?? "",
    location: variant?.contact.location ?? "",
    linksText: variant ? linksToText(variant.links) : "",
    isDefault: forceDefault || (variant?.is_default ?? false),
  });
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (!values.label.trim()) errors.label = "This field is required.";
    if (!values.fullName.trim()) errors.full_name = "This field is required.";
    setLocalErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setIsSubmitting(true);
    const committed = await onSubmit({
      label: values.label.trim(),
      full_name: values.fullName.trim(),
      contact: {
        email: values.email.trim() || null,
        phone: values.phone.trim() || null,
        location: values.location.trim() || null,
      },
      links: textToLinks(values.linksText),
      is_default: forceDefault ? true : values.isDefault,
    });
    setIsSubmitting(false);
    if (committed) onCancel();
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={variant ? "Edit variant" : "New variant"}
      className="border-border bg-card flex flex-col gap-3 rounded-lg border p-4"
    >
      <FormInputField
        label="Label"
        name="label"
        value={values.label}
        error={localErrors.label}
        onChange={(event) => setValues((prev) => ({ ...prev, label: event.target.value }))}
      />
      <FormInputField
        label="Full name"
        name="full_name"
        value={values.fullName}
        error={localErrors.full_name}
        onChange={(event) => setValues((prev) => ({ ...prev, fullName: event.target.value }))}
      />
      <FormInputField
        label="Email"
        name="email"
        type="email"
        value={values.email}
        onChange={(event) => setValues((prev) => ({ ...prev, email: event.target.value }))}
      />
      <FormInputField
        label="Phone"
        name="phone"
        value={values.phone}
        onChange={(event) => setValues((prev) => ({ ...prev, phone: event.target.value }))}
      />
      <FormInputField
        label="Location"
        name="location"
        value={values.location}
        onChange={(event) => setValues((prev) => ({ ...prev, location: event.target.value }))}
      />
      <label className="flex flex-col gap-1.5">
        <span className="text-foreground caption">Links</span>
        <textarea
          name="links"
          placeholder="Portfolio | https://example.dev"
          value={values.linksText}
          onChange={(event) => setValues((prev) => ({ ...prev, linksText: event.target.value }))}
          className="border-input bg-card text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 min-h-16 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
        />
      </label>
      <label className="caption flex items-center gap-2">
        <input
          type="checkbox"
          checked={forceDefault ? true : values.isDefault}
          disabled={forceDefault}
          onChange={(event) => setValues((prev) => ({ ...prev, isDefault: event.target.checked }))}
        />
        Default variant
        {forceDefault && <span className="text-muted-foreground">(your first variant)</span>}
      </label>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : variant ? "Save" : "Create"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
