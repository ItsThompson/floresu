import type { IdentityVariant } from "../types";

interface HeaderSectionProps {
  variants: IdentityVariant[];
  /** The variant the resume header currently references (living resumes). */
  selectedVariantId: number | null | undefined;
  isReadOnly: boolean;
  onSelect: (variantId: number | null) => void;
}

/**
 * The header/identity section: selects which identity variant the resume
 * resolves its contact facts from on render. A living resume references a
 * variant; a finalized resume has an inlined snapshot, so the selector is
 * read-only there.
 */
export function HeaderSection({ variants, selectedVariantId, isReadOnly, onSelect }: HeaderSectionProps) {
  const selectedLabel =
    variants.find((variant) => variant.id === selectedVariantId)?.label ?? "None selected";

  return (
    <section className="rounded-md border">
      <div className="border-b px-3 py-2 font-medium">Header / Identity</div>
      <div className="p-3">
        {isReadOnly ? (
          <p className="text-muted-foreground text-sm">Identity: {selectedLabel} (frozen)</p>
        ) : (
          <label className="flex flex-col gap-1.5">
            <span className="text-muted-foreground text-sm">Identity variant</span>
            <select
              className="border-input bg-background h-9 rounded-md border px-3 text-sm"
              value={selectedVariantId ?? ""}
              onChange={(event) => onSelect(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">None selected</option>
              {variants.map((variant) => (
                <option key={variant.id} value={variant.id}>
                  {variant.label}
                  {variant.is_default ? " (default)" : ""}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
    </section>
  );
}
