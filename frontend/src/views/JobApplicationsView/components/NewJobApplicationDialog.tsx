import { useState } from "react";

import { FormInputField } from "@/components/FormInputField";
import { Modal } from "@/components/Modal";
import { Button } from "@/components/ui/button";

interface NewJobApplicationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** Create the application; resolves to whether it succeeded. */
  onCreate: (company: string, roleTitle: string) => Promise<boolean>;
}

/**
 * Add a job application: a company and a role title. The new application starts
 * `added` with no linked resume (a resume is forked for it separately). A failed
 * create keeps the dialog open with an inline error and preserves the input.
 */
export function NewJobApplicationDialog({
  isOpen,
  onClose,
  onCreate,
}: NewJobApplicationDialogProps) {
  const [company, setCompany] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = !isSubmitting && company.trim() !== "" && roleTitle.trim() !== "";

  const submit = async () => {
    setIsSubmitting(true);
    setError(null);
    const ok = await onCreate(company.trim(), roleTitle.trim());
    setIsSubmitting(false);
    if (!ok) {
      setError("Could not add the job application. Please try again.");
      return;
    }
    setCompany("");
    setRoleTitle("");
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add a job application">
      <FormInputField
        label="Company"
        name="jobapp-company"
        placeholder="e.g. Acme Corp"
        value={company}
        onChange={(event) => setCompany(event.target.value)}
      />
      <FormInputField
        label="Role title"
        name="jobapp-role"
        placeholder="e.g. Senior Backend Engineer"
        value={roleTitle}
        onChange={(event) => setRoleTitle(event.target.value)}
      />

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" size="sm" onClick={() => void submit()} disabled={!canSubmit}>
          Add application
        </Button>
      </div>
    </Modal>
  );
}
