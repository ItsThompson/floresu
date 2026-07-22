import { useState, type FormEvent } from "react";

import { FormInputField } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";

import type { IdentityVariantRead, IdentityVariantWrite } from "../hooks/useIdentityVariants";
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
  const [label, setLabel] = useState(variant?.label ?? "");
  const [fullName, setFullName] = useState(variant?.full_name ?? "");
  const [email, setEmail] = useState(variant?.contact.email ?? "");
  const [phone, setPhone] = useState(variant?.contact.phone ?? "");
  const [location, setLocation] = useState(variant?.contact.location ?? "");
  const [linksText, setLinksText] = useState(variant ? linksToText(variant.links) : "");
  const [isDefault, setIsDefault] = useState(forceDefault || (variant?.is_default ?? false));
  const [missing, setMissing] = useState<{ label?: string; full_name?: string }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const errors: { label?: string; full_name?: string } = {};
    if (!label.trim()) errors.label = "This field is required.";
    if (!fullName.trim()) errors.full_name = "This field is required.";
    setMissing(errors);
    if (Object.keys(errors).length > 0) return;

    setIsSubmitting(true);
    const committed = await onSubmit({
      label: label.trim(),
      full_name: fullName.trim(),
      contact: {
        email: email.trim() || null,
        phone: phone.trim() || null,
        location: location.trim() || null,
      },
      links: textToLinks(linksText),
      is_default: forceDefault ? true : isDefault,
    });
    setIsSubmitting(false);
    if (committed) onCancel();
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={variant ? "Edit variant" : "New variant"}
      className="border-border flex flex-col gap-3 rounded-lg border p-4"
    >
      <FormInputField
        label="Label"
        name="label"
        value={label}
        error={missing.label}
        onChange={(event) => setLabel(event.target.value)}
      />
      <FormInputField
        label="Full name"
        name="full_name"
        value={fullName}
        error={missing.full_name}
        onChange={(event) => setFullName(event.target.value)}
      />
      <FormInputField
        label="Email"
        name="email"
        type="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <FormInputField
        label="Phone"
        name="phone"
        value={phone}
        onChange={(event) => setPhone(event.target.value)}
      />
      <FormInputField
        label="Location"
        name="location"
        value={location}
        onChange={(event) => setLocation(event.target.value)}
      />
      <label className="flex flex-col gap-1.5">
        <span className="text-foreground text-sm font-medium">Links</span>
        <textarea
          name="links"
          placeholder="Portfolio | https://example.dev"
          value={linksText}
          onChange={(event) => setLinksText(event.target.value)}
          className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 min-h-16 rounded-md border px-3 py-2 text-sm outline-none focus-visible:ring-[3px]"
        />
      </label>
      <label className="flex items-center gap-2 text-sm font-medium">
        <input
          type="checkbox"
          checked={forceDefault ? true : isDefault}
          disabled={forceDefault}
          onChange={(event) => setIsDefault(event.target.checked)}
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
