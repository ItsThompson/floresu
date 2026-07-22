import { ChevronRight } from "lucide-react";
import { Link } from "react-router";

import type { DragSourceProps, DragTargetProps } from "@/lib/reorder";

import { SECTION_PREVIEW_LIMIT } from "../constants";
import type { SkillRead } from "../types";
import { SectionCardShell } from "./SectionCardShell";

interface SkillsSectionCardProps {
  skills: SkillRead[];
  sourceProps: DragSourceProps;
  targetProps: DragTargetProps;
  isDragging: boolean;
}

/**
 * Hub preview of the curated skills list: each skill as a pill with its derived
 * usage count. Full add/rename/reorder/archive management lives behind the
 * "Manage" link, so this card stays a read-only preview.
 */
export function SkillsSectionCard({
  skills,
  sourceProps,
  targetProps,
  isDragging,
}: SkillsSectionCardProps) {
  const preview = skills.slice(0, SECTION_PREVIEW_LIMIT * 2);
  const overflow = skills.length - preview.length;

  return (
    <SectionCardShell
      title="Skills"
      sourceProps={sourceProps}
      targetProps={targetProps}
      isDragging={isDragging}
      headerAction={
        <Link
          to="/profile/skills"
          className="text-primary inline-flex items-center gap-0.5 text-sm font-medium hover:underline"
        >
          Manage <ChevronRight className="size-3.5" />
        </Link>
      }
    >
      {skills.length === 0 ? (
        <p className="text-muted-foreground text-sm">No skills yet.</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {preview.map((skill) => (
            <li
              key={skill.id}
              className="border-border bg-secondary text-secondary-foreground inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
            >
              <span className="font-medium">{skill.name}</span>
              <span className="text-muted-foreground">{skill.usage_count}</span>
            </li>
          ))}
        </ul>
      )}
      {overflow > 0 && <span className="text-muted-foreground text-xs">+{overflow} more</span>}
    </SectionCardShell>
  );
}
