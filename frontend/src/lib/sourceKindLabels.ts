import type { components } from "@/api";

type SourceKind = components["schemas"]["SourceKind"];

/**
 * Human labels for the four ground-truth source kinds. Shared by every surface
 * that names a kind (library browse groups, search result groups, the kind
 * filter) so a kind reads the same everywhere.
 */
export const SOURCE_KIND_LABELS: Record<SourceKind, string> = {
  role: "Role",
  project: "Project",
  certification: "Certification",
  education: "Education",
};
