import { useNavigate, useParams, useSearchParams } from "react-router";

import { Button } from "@/components/ui/button";

import { ContextualWorklogPanel } from "./components/ContextualWorklogPanel";
import { DetailShell } from "./components/DetailShell";
import { FramingsPanel } from "./components/FramingsPanel";
import { SourceForm } from "./components/SourceForm";
import { useContextualWorklog } from "./hooks/useContextualWorklog";
import { useSourceDetail } from "./hooks/useSourceDetail";
import { useSourceFramings } from "./hooks/useSourceFramings";
import { isSourceKind, SOURCE_KIND_CONFIGS } from "./sourceForm";

/**
 * The source detail screen. In create mode (`/profile/sources/new?kind=…`) it
 * shows only the basic-info form and routes to the real detail on success. In
 * edit mode (`/profile/sources/:id`) it is three columns: the basic-info form,
 * the bullet framings, and the source's contextual worklog. Business rules stay
 * on the backend; this view composes the pieces and surfaces write errors.
 */
export function ProfileSourceDetailView() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const sourceId = params.sourceId ? Number(params.sourceId) : null;
  const createKindParam = searchParams.get("kind");
  const createKind = isSourceKind(createKindParam) ? createKindParam : null;

  const detail = useSourceDetail({
    sourceId,
    createKind,
    onCreated: (id) => navigate(`/profile/sources/${id}`, { replace: true }),
    onArchived: () => navigate("/profile"),
  });
  const framings = useSourceFramings(sourceId);
  const worklog = useContextualWorklog(sourceId);

  const isCreate = sourceId === null;

  if (isCreate && !createKind) {
    return (
      <DetailShell>
        <p role="alert" className="text-destructive text-sm">
          Unknown source kind. Pick a section to add to from your profile.
        </p>
      </DetailShell>
    );
  }

  if (detail.status === "loading") {
    return (
      <DetailShell>
        <p className="text-muted-foreground text-sm">Loading…</p>
      </DetailShell>
    );
  }

  if (detail.status === "error" || !detail.kind || !detail.initial) {
    return (
      <DetailShell>
        <p role="alert" className="text-destructive text-sm">
          Could not load this source.
        </p>
      </DetailShell>
    );
  }

  const title = isCreate
    ? `New ${SOURCE_KIND_CONFIGS[detail.kind].singular}`
    : (detail.record?.display_label ?? "Source");

  const form = (
    <SourceForm
      fields={SOURCE_KIND_CONFIGS[detail.kind].fields}
      initialValues={detail.initial.values}
      initialOngoing={detail.initial.ongoing}
      isSaving={detail.write.status === "saving"}
      serverErrors={detail.fieldErrors}
      saveError={detail.write.status === "error" ? detail.write.message : null}
      submitLabel={isCreate ? "Create" : "Save changes"}
      onSubmit={detail.save}
    />
  );

  return (
    <DetailShell
      title={title}
      action={
        !isCreate && (
          <Button type="button" variant="outline" size="sm" onClick={detail.archive}>
            Archive
          </Button>
        )
      }
    >
      {isCreate ? (
        <div className="max-w-lg">{form}</div>
      ) : (
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          {form}
          <FramingsPanel framings={framings} />
          <ContextualWorklogPanel worklog={worklog} />
        </div>
      )}
    </DetailShell>
  );
}
