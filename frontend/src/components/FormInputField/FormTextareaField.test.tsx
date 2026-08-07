import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FormTextareaField } from "./FormTextareaField";

describe("FormTextareaField", () => {
  it("renders the label wired to the textarea", () => {
    render(<FormTextareaField label="Statement" name="statement" rows={3} />);
    const textarea = screen.getByLabelText("Statement");
    expect(textarea.tagName).toBe("TEXTAREA");
    expect(textarea).toHaveAttribute("name", "statement");
    expect(textarea).toHaveAttribute("rows", "3");
    expect(textarea).not.toHaveAttribute("aria-invalid");
  });

  it("renders a field error and marks the textarea invalid", () => {
    render(<FormTextareaField label="Statement" name="statement" error="Say something." />);
    const textarea = screen.getByLabelText("Statement");
    expect(textarea).toHaveAttribute("aria-invalid", "true");
    const error = screen.getByRole("alert");
    expect(error).toHaveTextContent("Say something.");
    expect(textarea).toHaveAttribute("aria-describedby", error.id);
  });

  // The invalid border is the pairing a restated class string loses first, so the
  // shared shape is asserted here rather than trusted.
  it("carries the invalid-border pairing from the shared field shape", () => {
    render(<FormTextareaField label="Statement" name="statement" />);
    expect(screen.getByLabelText("Statement")).toHaveClass("aria-invalid:border-destructive");
  });

  it("names the field from a hidden label without drawing it", () => {
    render(<FormTextareaField label="Bullet text" labelVisibility="hidden" />);
    const textarea = screen.getByLabelText("Bullet text");
    expect(screen.getByText("Bullet text")).toHaveClass("sr-only");
    expect(textarea).toBeInTheDocument();
  });

  // A section repeats this field once per item, so two unnamed fields must not
  // share one id: a shared id would point both labels at the first textarea.
  it("gives each unnamed field its own id", () => {
    render(
      <>
        <FormTextareaField label="Bullet text" labelVisibility="hidden" defaultValue="first" />
        <FormTextareaField label="Bullet text" labelVisibility="hidden" defaultValue="second" />
      </>,
    );
    const [first, second] = screen.getAllByLabelText("Bullet text");
    expect(first).toHaveValue("first");
    expect(second).toHaveValue("second");
    expect(first.id).not.toBe(second.id);
  });
});
