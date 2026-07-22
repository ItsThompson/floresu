import { ChevronRight, Star } from "lucide-react";
import { Link } from "react-router";

import type { DragSourceProps, DragTargetProps } from "@/lib/reorder";

import { SECTION_PREVIEW_LIMIT } from "../constants";
import type { IdentityVariantRead } from "../types";
import { SectionCardShell } from "./SectionCardShell";

interface IdentitySectionCardProps {
  variants: IdentityVariantRead[];
  sourceProps: DragSourceProps;
  targetProps: DragTargetProps;
  isDragging: boolean;
}

/**
 * Hub preview of the identity variants (the labeled contact sets a resume
 * projects), marking the default. Create/edit/set-default/archive management
 * lives behind the "Manage" link.
 */
export function IdentitySectionCard({
  variants,
  sourceProps,
  targetProps,
  isDragging,
}: IdentitySectionCardProps) {
  const preview = variants.slice(0, SECTION_PREVIEW_LIMIT);
  const overflow = variants.length - preview.length;

  return (
    <SectionCardShell
      title="Identity"
      sourceProps={sourceProps}
      targetProps={targetProps}
      isDragging={isDragging}
      headerAction={
        <Link
          to="/profile/identities"
          className="text-primary inline-flex items-center gap-0.5 text-sm font-medium hover:underline"
        >
          Manage <ChevronRight className="size-3.5" />
        </Link>
      }
    >
      {variants.length === 0 ? (
        <p className="text-muted-foreground text-sm">No identity variants yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {preview.map((variant) => (
            <li key={variant.id} className="flex items-center gap-2 text-sm">
              <span className="truncate font-medium">{variant.label}</span>
              {variant.is_default && (
                <span className="text-muted-foreground inline-flex items-center gap-0.5 text-xs">
                  <Star className="size-3 fill-current" /> Default
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {overflow > 0 && <span className="text-muted-foreground text-xs">+{overflow} more</span>}
    </SectionCardShell>
  );
}
