import type { DragSourceProps, DragTargetProps } from "@/lib/reorder";

import type { SourceSectionConfig } from "../constants";
import type { SourceKind, SourceSummary } from "../types";
import { SectionCardShell } from "./SectionCardShell";
import { SourceGroupList } from "./SourceGroupList";

interface SourceSectionCardProps {
  config: SourceSectionConfig;
  /** All active sources; this card filters to its own kinds. */
  sources: SourceSummary[];
  sectionSource: DragSourceProps;
  sectionTarget: DragTargetProps;
  isDragging: boolean;
  onReorderItems: (kind: SourceKind, orderedIds: number[]) => void;
  onArchive: (id: number) => void;
}

/**
 * A hub card for one or more source kinds. The card is reorderable among the
 * other section cards; each kind inside it is an independently reorderable group.
 */
export function SourceSectionCard({
  config,
  sources,
  sectionSource,
  sectionTarget,
  isDragging,
  onReorderItems,
  onArchive,
}: SourceSectionCardProps) {
  return (
    <SectionCardShell
      title={config.title}
      sourceProps={sectionSource}
      targetProps={sectionTarget}
      isDragging={isDragging}
    >
      {config.groups.map((group) => (
        <SourceGroupList
          key={group.kind}
          kind={group.kind}
          label={group.label}
          sources={sortByOrder(sources, group.kind)}
          onReorder={onReorderItems}
          onArchive={onArchive}
        />
      ))}
    </SectionCardShell>
  );
}

function sortByOrder(sources: SourceSummary[], kind: SourceKind): SourceSummary[] {
  return sources
    .filter((source) => source.kind === kind)
    .sort((left, right) => left.sort_order - right.sort_order);
}
