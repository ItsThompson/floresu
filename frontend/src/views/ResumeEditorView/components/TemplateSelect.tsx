import { FIELD_SHAPE_CLASS } from "@/components/FormInputField";
import { cn } from "@/lib/utils";

import type { TemplateInfo } from "../types";

interface TemplateSelectProps {
  templates: TemplateInfo[];
  selectedTemplateId: string;
  isReadOnly: boolean;
  onChange: (templateId: string) => void;
}

/**
 * Template selector. Changing the template re-renders the same content with a
 * different layout; colors and fonts are fixed by each template and cannot be
 * overridden, so there is no color or font control here.
 */
export function TemplateSelect({
  templates,
  selectedTemplateId,
  isReadOnly,
  onChange,
}: TemplateSelectProps) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-muted-foreground caption">Template</span>
      <select
        aria-label="Template"
        disabled={isReadOnly}
        value={selectedTemplateId}
        onChange={(event) => onChange(event.target.value)}
        className={cn(FIELD_SHAPE_CLASS, "h-8 px-2 disabled:opacity-50")}
      >
        {templates.map((template) => (
          <option key={template.id} value={template.id}>
            {template.name}
          </option>
        ))}
      </select>
    </label>
  );
}
