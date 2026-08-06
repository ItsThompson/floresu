import type { ComponentProps, Ref } from "react";

import { cn } from "@/lib/utils";

import { FIELD_LABEL_CLASS, FIELD_SHAPE_CLASS } from "./constants";

interface FormInputFieldProps extends ComponentProps<"input"> {
  label: string;
  error?: string;
  ref?: Ref<HTMLInputElement>;
}

/**
 * A labeled text input that renders an inline field-level error and wires the
 * accessibility relationship (`aria-invalid` + `aria-describedby`). Field errors
 * come from the RFC 9457 `fields` map; the entered value is preserved on the
 * caller's controlled state, so a failed write never clears the form.
 */
export function FormInputField({ label, error, id, name, ref, ...props }: FormInputFieldProps) {
  const inputId = id ?? name;
  const errorId = error ? `${inputId}-error` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className={FIELD_LABEL_CLASS}>
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        className={cn(FIELD_SHAPE_CLASS, "h-9 px-3")}
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
