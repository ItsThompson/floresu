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
 * Email + password login. Field-level RFC 9457 errors attach to their input; a
 * wrong-credentials 401 renders as a single generic message (the backend never
 * says whether the email exists). Entered values are preserved on failure.
 */
export function LoginForm() {
  const { login } = useAuth();
  const [values, setValues] = useState<Credentials>(EMPTY);
  const [submit, setSubmit] = useState<SubmitStatus>({ phase: "idle" });
  const fieldErrors = submit.phase === "error" ? submit.fields : {};
  const hasFieldErrors = Object.values(fieldErrors).some(Boolean);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!values.email || !values.password) {
      setSubmit({ phase: "error", message: "Enter your email and password.", fields: {} });
      return;
    }
    setSubmit({ phase: "submitting" });
    const result = await login(values);
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
        autoComplete="current-password"
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
        {submit.phase === "submitting" ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
