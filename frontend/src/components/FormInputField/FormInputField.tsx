import type { ComponentProps, Ref } from "react";

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
      <label htmlFor={inputId} className="text-foreground text-sm font-medium">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        name={name}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive h-9 rounded-md border px-3 text-sm outline-none focus-visible:ring-[3px]"
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
