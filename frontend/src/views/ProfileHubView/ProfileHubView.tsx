import { useNavigate } from "react-router";
import type { ReactNode } from "react";

import { ErrorBanner } from "@/components/ErrorBanner";
import { useDragReorder, type DragSourceProps, type DragTargetProps } from "@/lib/reorder";

import { SOURCE_SECTIONS } from "./constants";
import { IdentitySectionCard } from "./components/IdentitySectionCard";
import { ProfileSearchField } from "./components/ProfileSearchField";
import { SkillsSectionCard } from "./components/SkillsSectionCard";
import { SourceSectionCard } from "./components/SourceSectionCard";
import { useProfileHub } from "./hooks/useProfileHub";
import { useSectionOrder } from "./hooks/useSectionOrder";
import type { HubData, ProfileHubActions, SectionId } from "./types";

/**
 * The Career Profile hub: a card grid of profile sections (work, projects,
 * skills, education/certs, identity). Section cards reorder by drag and persist;
 * the source cards' items reorder per kind and archive; skills and identity
 * previews route to their management surfaces. The search field emits its query
 * to the Library search.
 *
 * A two-column card grid, not a reading column, so it takes a wide cap rather
 * than the `reading-width` measure.
 */
export function ProfileHubView() {
  const { state, actions } = useProfileHub();
  const { order, reorder } = useSectionOrder();
  const navigate = useNavigate();
  const sectionDrag = useDragReorder(order, (next) => reorder(next as SectionId[]));

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Career Profile</h1>
        <ProfileSearchField
          onSearch={(query) => navigate(`/library?q=${encodeURIComponent(query)}`)}
        />
      </header>

      {state.status === "loading" && (
        <p className="text-muted-foreground text-sm">Loading your profile…</p>
      )}

      {state.status === "error" && (
        <p role="alert" className="text-destructive text-sm">
          Could not load your profile. Please try again.
        </p>
      )}

      {state.actionError && (
        <ErrorBanner message={state.actionError} onDismiss={actions.dismissError} />
      )}

      {state.status === "ready" && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {order.map((sectionId) =>
            renderSection(sectionId, state.data, actions, {
              sourceProps: sectionDrag.sourceProps(sectionId),
              targetProps: sectionDrag.targetProps(sectionId),
              isDragging: sectionDrag.draggingId === sectionId,
            }),
          )}
        </div>
      )}
    </section>
  );
}

interface SectionDragProps {
  sourceProps: DragSourceProps;
  targetProps: DragTargetProps;
  isDragging: boolean;
}

/** Compose the correct card for a section id; view composition, not a data rule. */
function renderSection(
  sectionId: SectionId,
  data: HubData,
  actions: ProfileHubActions,
  drag: SectionDragProps,
): ReactNode {
  if (sectionId === "skills") {
    return (
      <SkillsSectionCard
        key={sectionId}
        skills={data.skills}
        sourceProps={drag.sourceProps}
        targetProps={drag.targetProps}
        isDragging={drag.isDragging}
      />
    );
  }
  if (sectionId === "identity") {
    return (
      <IdentitySectionCard
        key={sectionId}
        variants={data.variants}
        sourceProps={drag.sourceProps}
        targetProps={drag.targetProps}
        isDragging={drag.isDragging}
      />
    );
  }
  const config = SOURCE_SECTIONS.find((section) => section.id === sectionId);
  if (!config) return null;
  return (
    <SourceSectionCard
      key={sectionId}
      config={config}
      sources={data.sources}
      sectionSource={drag.sourceProps}
      sectionTarget={drag.targetProps}
      isDragging={drag.isDragging}
      onReorderItems={actions.reorderSources}
      onArchive={actions.archiveSource}
    />
  );
}
