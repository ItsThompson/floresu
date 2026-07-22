import { Archive, Pencil, Star } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { IdentityVariantRead } from "../hooks/useIdentityVariants";

interface VariantRowProps {
  variant: IdentityVariantRead;
  onEdit: (id: number) => void;
  onSetDefault: (id: number) => void;
  onArchive: (id: number) => void;
}

/**
 * One identity variant row: label, name, contact preview, and controls to edit,
 * set default, and archive. The default is marked and its archive control is
 * disabled, since the default cannot be archived until another is made default.
 */
export function VariantRow({ variant, onEdit, onSetDefault, onArchive }: VariantRowProps) {
  return (
    <li className="border-border flex items-center gap-3 rounded-md border px-3 py-2">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{variant.label}</span>
          {variant.is_default && (
            <span className="text-muted-foreground inline-flex items-center gap-0.5 text-xs">
              <Star className="size-3 fill-current" /> Default
            </span>
          )}
        </div>
        <span className="text-muted-foreground truncate text-xs">
          {variant.full_name}
          {variant.contact.email ? ` · ${variant.contact.email}` : ""}
        </span>
      </div>

      {!variant.is_default && (
        <Button type="button" size="sm" variant="ghost" onClick={() => onSetDefault(variant.id)}>
          Set default
        </Button>
      )}
      <button
        type="button"
        aria-label={`Edit ${variant.label}`}
        onClick={() => onEdit(variant.id)}
        className="text-muted-foreground hover:text-foreground rounded p-1"
      >
        <Pencil className="size-3.5" />
      </button>
      <button
        type="button"
        aria-label={`Archive ${variant.label}`}
        onClick={() => onArchive(variant.id)}
        disabled={variant.is_default}
        title={variant.is_default ? "Make another variant the default first" : undefined}
        className="text-muted-foreground hover:text-destructive rounded p-1 disabled:opacity-40"
      >
        <Archive className="size-3.5" />
      </button>
    </li>
  );
}
