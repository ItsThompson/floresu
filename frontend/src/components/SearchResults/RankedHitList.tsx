import { Link } from "react-router";

import { libraryBulletHref, sourceDetailHref } from "@/lib/entityPaths";

import type { RankedRow } from "./rankedRows";

interface RankedHitListProps {
  rows: RankedRow[];
}

const TYPE_LABELS: Record<RankedRow["type"], string> = {
  worklog: "Worklog",
  bullet: "Bullet",
  source: "Source",
};

// A worklog hit has no page of its own, so it is the one kind whose label
// renders as plain text.
const HIT_HREF_BUILDERS: Partial<Record<RankedRow["type"], (id: number) => string>> = {
  bullet: libraryBulletHref,
  source: sourceDetailHref,
};

/**
 * The flat RRF-ranked relevance list: every hit in ranked order, each tagged
 * with its kind, linked to where it lives, and carrying its secondary detail.
 * This is where a hit with no source (an unattached worklog entry or bullet)
 * still surfaces, since the grouped view lists only sources: for a worklog hit
 * it is the only place its date is ever shown.
 */
export function RankedHitList({ rows }: RankedHitListProps) {
  return (
    <ol className="flex flex-col gap-2">
      {rows.map((row) => {
        const buildHref = HIT_HREF_BUILDERS[row.type];
        const detail = row.detail;
        return (
          <li
            key={row.key}
            className="border-border flex items-start gap-2 rounded-md border p-3 text-sm"
          >
            <span className="mono-tag text-muted-foreground shrink-0 pt-1">
              {TYPE_LABELS[row.type]}
            </span>
            <span className="min-w-0">
              {buildHref ? (
                <Link
                  to={buildHref(row.id)}
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {row.label}
                </Link>
              ) : (
                row.label
              )}
              {detail !== null && (
                <span className="mono-meta text-muted-foreground ml-2">
                  {detail.dateTime === null ? (
                    detail.text
                  ) : (
                    <time dateTime={detail.dateTime}>{detail.text}</time>
                  )}
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
