import { describe, expect, it } from "vitest";

import { emptyValues, isSourceKind, SOURCE_KIND_CONFIGS } from "./sourceForm";
import type { SourceFormValues, SourceKind, SourceRecord, SourceWrite } from "./types";

/**
 * Table-driven coverage of the per-kind form strategy: each kind's `buildWrite`
 * (form values -> typed write body) and `toValues` (record -> form values), plus
 * the empty-form and kind-guard helpers. Roles derive their display label from
 * company and title; the other kinds carry it as a field.
 */

interface BuildCase {
  kind: SourceKind;
  values: SourceFormValues;
  ongoing: boolean;
  expected: SourceWrite;
}

const buildCases: BuildCase[] = [
  {
    kind: "role",
    values: {
      company: " Acme ",
      job_title: " Engineer ",
      title_aliases: "SWE II, UI Dev, ",
      location: "Remote",
      date_start: "2024-01-01",
      date_end: "",
      summary: "Built things.",
    },
    ongoing: true,
    expected: {
      kind: "role",
      display_label: "Acme — Engineer",
      company: "Acme",
      job_title: "Engineer",
      title_aliases: ["SWE II", "UI Dev"],
      location: "Remote",
      date_start: "2024-01-01",
      date_end: null, // ongoing wins over any typed end date
      summary: "Built things.",
    },
  },
  {
    kind: "project",
    values: {
      display_label: "StudyBoost",
      links: "https://a.dev, https://b.dev",
      date_start: "",
      date_end: "2024-06-01",
      summary: "",
    },
    ongoing: false,
    expected: {
      kind: "project",
      display_label: "StudyBoost",
      links: ["https://a.dev", "https://b.dev"],
      date_start: null,
      date_end: "2024-06-01",
      summary: null,
    },
  },
  {
    kind: "certification",
    values: {
      display_label: "AWS SAA",
      issuer: "Amazon",
      credential_id: "",
      date_start: "2023-05-01",
      date_end: "",
      summary: "",
    },
    ongoing: false,
    expected: {
      kind: "certification",
      display_label: "AWS SAA",
      issuer: "Amazon",
      credential_id: null, // empty optional -> null, not ongoing
      date_start: "2023-05-01",
      date_end: null,
      summary: null,
    },
  },
  {
    kind: "education",
    values: {
      display_label: "BSc Computer Science",
      institution: "University of Bath",
      degree: "",
      field: "",
      date_start: "2019-09-01",
      date_end: "2022-06-01",
      summary: "First class.",
    },
    ongoing: false,
    expected: {
      kind: "education",
      display_label: "BSc Computer Science",
      institution: "University of Bath",
      degree: null,
      field: null,
      date_start: "2019-09-01",
      date_end: "2022-06-01",
      summary: "First class.",
    },
  },
];

describe("SOURCE_KIND_CONFIGS.buildWrite", () => {
  it.each(buildCases)("builds the $kind write body", ({ kind, values, ongoing, expected }) => {
    expect(SOURCE_KIND_CONFIGS[kind].buildWrite(values, ongoing)).toEqual(expected);
  });
});

interface ToValuesCase {
  kind: SourceKind;
  record: SourceRecord;
  expected: { values: SourceFormValues; ongoing: boolean };
}

const toValuesCases: ToValuesCase[] = [
  {
    kind: "role",
    record: {
      id: 1,
      kind: "role",
      display_label: "Acme — Engineer",
      date_start: "2024-01-01",
      date_end: null,
      summary: "Built things.",
      sort_order: 0,
      archived_at: null,
      detail: { company: "Acme", job_title: "Engineer", title_aliases: ["SWE II"], location: "Remote" },
    },
    expected: {
      ongoing: true, // null end date -> ongoing
      values: {
        date_start: "2024-01-01",
        date_end: "",
        summary: "Built things.",
        company: "Acme",
        job_title: "Engineer",
        title_aliases: "SWE II",
        location: "Remote",
      },
    },
  },
  {
    kind: "project",
    record: {
      id: 2,
      kind: "project",
      display_label: "StudyBoost",
      date_start: null,
      date_end: "2024-06-01",
      summary: null,
      sort_order: 0,
      archived_at: null,
      detail: { links: ["https://a.dev"] },
    },
    expected: {
      ongoing: false,
      values: {
        date_start: "",
        date_end: "2024-06-01",
        summary: "",
        display_label: "StudyBoost",
        links: "https://a.dev",
      },
    },
  },
  {
    kind: "certification",
    record: {
      id: 3,
      kind: "certification",
      display_label: "AWS SAA",
      date_start: "2023-05-01",
      date_end: null,
      summary: null,
      sort_order: 0,
      archived_at: null,
      detail: { issuer: "Amazon", credential_id: null },
    },
    expected: {
      ongoing: true,
      values: {
        date_start: "2023-05-01",
        date_end: "",
        summary: "",
        display_label: "AWS SAA",
        issuer: "Amazon",
        credential_id: "",
      },
    },
  },
  {
    kind: "education",
    record: {
      id: 4,
      kind: "education",
      display_label: "BSc Computer Science",
      date_start: "2019-09-01",
      date_end: "2022-06-01",
      summary: "First class.",
      sort_order: 0,
      archived_at: null,
      detail: { institution: "University of Bath", degree: null, field: null },
    },
    expected: {
      ongoing: false,
      values: {
        date_start: "2019-09-01",
        date_end: "2022-06-01",
        summary: "First class.",
        display_label: "BSc Computer Science",
        institution: "University of Bath",
        degree: "",
        field: "",
      },
    },
  },
];

describe("SOURCE_KIND_CONFIGS.toValues", () => {
  it.each(toValuesCases)("hydrates the form from a $kind record", ({ kind, record, expected }) => {
    expect(SOURCE_KIND_CONFIGS[kind].toValues(record)).toEqual(expected);
  });

  it("round-trips a record through toValues then buildWrite for every kind", () => {
    for (const { kind, record } of toValuesCases) {
      const { values, ongoing } = SOURCE_KIND_CONFIGS[kind].toValues(record);
      const write = SOURCE_KIND_CONFIGS[kind].buildWrite(values, ongoing);
      expect(write.kind).toBe(kind);
      expect(write.display_label).toBe(record.display_label);
      expect(write.date_end).toBe(record.date_end);
    }
  });
});

describe("emptyValues", () => {
  it.each(["role", "project", "certification", "education"] as const)(
    "seeds every %s field plus the common fields empty",
    (kind) => {
      const { values, ongoing } = emptyValues(kind);
      expect(ongoing).toBe(false);
      for (const field of SOURCE_KIND_CONFIGS[kind].fields) {
        expect(values[field.name]).toBe("");
      }
      expect(values.date_start).toBe("");
      expect(values.date_end).toBe("");
      expect(values.summary).toBe("");
    },
  );
});

describe("isSourceKind", () => {
  it("accepts the four source kinds and rejects anything else", () => {
    for (const kind of ["role", "project", "certification", "education"]) {
      expect(isSourceKind(kind)).toBe(true);
    }
    expect(isSourceKind("skill")).toBe(false);
    expect(isSourceKind(null)).toBe(false);
  });
});
