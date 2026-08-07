import { useId, type ComponentProps, type Ref } from "react";

import { cn } from "@/lib/utils";

import { FIELD_LABEL_CLASS, FIELD_SHAPE_CLASS } from "./constants";

interface FormTextareaFieldProps extends ComponentProps<"textarea"> {
  label: string;
  error?: string;
  /**
   * `hidden` keeps the label in the DOM, so the field still takes its accessible
   * name from it, but off screen. Dense rows that repeat one field per item read
   * as noise with the label drawn every time.
   */
  labelVisibility?: "visible" | "hidden";
  ref?: Ref<HTMLTextAreaElement>;
}

/**
 * The multi-line sibling of `FormInputField`: same label, same field shape, same
 * inline field-level error and `aria-invalid` + `aria-describedby` wiring. Height
 * comes from `rows`, so a caller sets how tall the field starts without restating
 * the shape.
 */
export function FormTextareaField({
  label,
  error,
  labelVisibility = "visible",
  id,
  name,
  className,
  ref,
  ...props
}: FormTextareaFieldProps) {
  const fallbackId = useId();
  const textareaId = id ?? name ?? fallbackId;
  const errorId = error ? `${textareaId}-error` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={textareaId}
        className={labelVisibility === "hidden" ? "sr-only" : FIELD_LABEL_CLASS}
      >
        {label}
      </label>
      <textarea
        ref={ref}
        id={textareaId}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        className={cn(FIELD_SHAPE_CLASS, "w-full resize-y px-3 py-2", className)}
        {...props}
      />
      {error && (
        <span id={errorId} role="alert" className="text-destructive text-sm">
          {error}
        </span>
      )}
    </div>
  );
}
