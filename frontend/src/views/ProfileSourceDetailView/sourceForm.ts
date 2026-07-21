import type {
  CertificationDetail,
  EducationDetail,
  ProjectDetail,
  RoleDetail,
  SourceFormValues,
  SourceKind,
  SourceRecord,
  SourceWrite,
} from "./types";

/**
 * The per-kind form strategy. Each source kind declares its own labeled fields
 * and how to build its typed write body and hydrate the form from a record. The
 * form component renders these descriptors generically and stays kind-agnostic,
 * so a new kind is a config entry, not a new branch in the form.
 *
 * Dates and summary are common to every kind and rendered by the form itself;
 * `fields` holds only the kind-specific inputs. `display_label` is the source
 * headline: kinds that expose it as an editable field list it here; roles derive
 * it from company and title instead.
 */

type FieldType = "text" | "textarea" | "csv";

export interface SourceFieldDesc {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  placeholder?: string;
}

export interface SourceKindConfig {
  kind: SourceKind;
  /** The section title shown in create mode ("New role"). */
  singular: string;
  fields: SourceFieldDesc[];
  buildWrite: (values: SourceFormValues, ongoing: boolean) => SourceWrite;
  toValues: (record: SourceRecord) => { values: SourceFormValues; ongoing: boolean };
}

const csvToList = (value: string): string[] =>
  value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);

const listToCsv = (list: string[]): string => list.join(", ");

const orNull = (value: string | undefined): string | null => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
};

/** date_end is null when the source is ongoing (rendered "Present" downstream). */
const endDate = (values: SourceFormValues, ongoing: boolean): string | null =>
  ongoing ? null : orNull(values.date_end);

const commonValues = (record: SourceRecord): { base: SourceFormValues; ongoing: boolean } => ({
  base: {
    date_start: record.date_start ?? "",
    date_end: record.date_end ?? "",
    summary: record.summary ?? "",
  },
  ongoing: record.date_end === null,
});

export const SOURCE_KIND_CONFIGS: Record<SourceKind, SourceKindConfig> = {
  role: {
    kind: "role",
    singular: "role",
    fields: [
      { name: "company", label: "Company", type: "text", required: true },
      { name: "job_title", label: "Job title", type: "text", required: true },
      { name: "title_aliases", label: "Title aliases", type: "csv", placeholder: "SWE II, UI Dev" },
      { name: "location", label: "Location", type: "text" },
    ],
    buildWrite: (values, ongoing) => ({
      kind: "role",
      display_label: `${values.company?.trim() ?? ""} — ${values.job_title?.trim() ?? ""}`,
      company: values.company?.trim() ?? "",
      job_title: values.job_title?.trim() ?? "",
      title_aliases: csvToList(values.title_aliases ?? ""),
      location: orNull(values.location),
      date_start: orNull(values.date_start),
      date_end: endDate(values, ongoing),
      summary: orNull(values.summary),
    }),
    toValues: (record) => {
      const detail = record.detail as RoleDetail;
      const { base, ongoing } = commonValues(record);
      return {
        ongoing,
        values: {
          ...base,
          company: detail.company,
          job_title: detail.job_title,
          title_aliases: listToCsv(detail.title_aliases),
          location: detail.location ?? "",
        },
      };
    },
  },
  project: {
    kind: "project",
    singular: "project",
    fields: [
      { name: "display_label", label: "Project name", type: "text", required: true },
      { name: "links", label: "Links", type: "csv", placeholder: "https://…, https://…" },
    ],
    buildWrite: (values, ongoing) => ({
      kind: "project",
      display_label: values.display_label?.trim() ?? "",
      links: csvToList(values.links ?? ""),
      date_start: orNull(values.date_start),
      date_end: endDate(values, ongoing),
      summary: orNull(values.summary),
    }),
    toValues: (record) => {
      const detail = record.detail as ProjectDetail;
      const { base, ongoing } = commonValues(record);
      return {
        ongoing,
        values: { ...base, display_label: record.display_label, links: listToCsv(detail.links) },
      };
    },
  },
  certification: {
    kind: "certification",
    singular: "certification",
    fields: [
      { name: "display_label", label: "Name", type: "text", required: true },
      { name: "issuer", label: "Issuer", type: "text", required: true },
      { name: "credential_id", label: "Credential ID", type: "text" },
    ],
    buildWrite: (values, ongoing) => ({
      kind: "certification",
      display_label: values.display_label?.trim() ?? "",
      issuer: values.issuer?.trim() ?? "",
      credential_id: orNull(values.credential_id),
      date_start: orNull(values.date_start),
      date_end: endDate(values, ongoing),
      summary: orNull(values.summary),
    }),
    toValues: (record) => {
      const detail = record.detail as CertificationDetail;
      const { base, ongoing } = commonValues(record);
      return {
        ongoing,
        values: {
          ...base,
          display_label: record.display_label,
          issuer: detail.issuer,
          credential_id: detail.credential_id ?? "",
        },
      };
    },
  },
  education: {
    kind: "education",
    singular: "education",
    fields: [
      { name: "display_label", label: "Title", type: "text", required: true },
      { name: "institution", label: "Institution", type: "text", required: true },
      { name: "degree", label: "Degree", type: "text" },
      { name: "field", label: "Field", type: "text" },
    ],
    buildWrite: (values, ongoing) => ({
      kind: "education",
      display_label: values.display_label?.trim() ?? "",
      institution: values.institution?.trim() ?? "",
      degree: orNull(values.degree),
      field: orNull(values.field),
      date_start: orNull(values.date_start),
      date_end: endDate(values, ongoing),
      summary: orNull(values.summary),
    }),
    toValues: (record) => {
      const detail = record.detail as EducationDetail;
      const { base, ongoing } = commonValues(record);
      return {
        ongoing,
        values: {
          ...base,
          display_label: record.display_label,
          institution: detail.institution,
          degree: detail.degree ?? "",
          field: detail.field ?? "",
        },
      };
    },
  },
};

export function isSourceKind(value: string | null): value is SourceKind {
  return value === "role" || value === "project" || value === "certification" || value === "education";
}

/** The empty form state for a new source of the given kind. */
export function emptyValues(kind: SourceKind): { values: SourceFormValues; ongoing: boolean } {
  const base: SourceFormValues = { date_start: "", date_end: "", summary: "" };
  const values = SOURCE_KIND_CONFIGS[kind].fields.reduce<SourceFormValues>(
    (acc, field) => ({ ...acc, [field.name]: "" }),
    base,
  );
  return { values, ongoing: false };
}
