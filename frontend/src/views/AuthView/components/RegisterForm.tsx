import { useState, type FormEvent } from "react";

import { useAuth } from "@/auth";
import { FormInputField } from "@/components/FormInputField";
import { Button } from "@/components/ui/button";
import type { SubmitStatus } from "../types";

interface Credentials {
  email: string;
  password: string;
}

const EMPTY: Credentials = { email: "", password: "" };

/**
 * Email + password registration. A duplicate-email 409 and a weak-password 422
 * attach their RFC 9457 field errors to the offending input; entered values are
 * preserved on failure so the user can correct and retry.
 */
export function RegisterForm() {
  const { register } = useAuth();
  const [values, setValues] = useState<Credentials>(EMPTY);
  const [submit, setSubmit] = useState<SubmitStatus>({ phase: "idle" });
  const fieldErrors = submit.phase === "error" ? submit.fields : {};
  const hasFieldErrors = Object.values(fieldErrors).some(Boolean);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!values.email || !values.password) {
      setSubmit({ phase: "error", message: "Enter an email and a password.", fields: {} });
      return;
    }
    setSubmit({ phase: "submitting" });
    const result = await register(values);
    if (result.ok) {
      setSubmit({ phase: "idle" });
      return;
    }
    setSubmit({ phase: "error", message: result.message, fields: result.fields ?? {} });
  };

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <FormInputField
        label="Email"
        type="email"
        name="email"
        autoComplete="email"
        value={values.email}
        error={fieldErrors.email}
        onChange={(event) => setValues((prev) => ({ ...prev, email: event.target.value }))}
      />
      <FormInputField
        label="Password"
        type="password"
        name="password"
        autoComplete="new-password"
        value={values.password}
        error={fieldErrors.password}
        onChange={(event) => setValues((prev) => ({ ...prev, password: event.target.value }))}
      />
      {submit.phase === "error" && !hasFieldErrors && (
        <p role="alert" className="text-destructive text-sm">
          {submit.message}
        </p>
      )}
      <Button type="submit" disabled={submit.phase === "submitting"}>
        {submit.phase === "submitting" ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
