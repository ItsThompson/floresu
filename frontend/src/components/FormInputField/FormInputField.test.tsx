import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FormInputField } from "./FormInputField";

describe("FormInputField", () => {
  it("renders the label wired to the input", () => {
    render(<FormInputField label="Email" name="email" type="email" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("name", "email");
    expect(input).not.toHaveAttribute("aria-invalid");
  });

  it("renders a field error and marks the input invalid", () => {
    render(<FormInputField label="Email" name="email" error="This email is already registered." />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const error = screen.getByRole("alert");
    expect(error).toHaveTextContent("This email is already registered.");
    // The input is described by the error node for assistive tech.
    expect(input).toHaveAttribute("aria-describedby", error.id);
  });
});
