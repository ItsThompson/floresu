import type { components } from "@/api";

export type SourceKind = components["schemas"]["SourceKind"];
export type SourceRecord = components["schemas"]["SourceRecord"];
export type RoleDetail = components["schemas"]["RoleDetail"];
export type ProjectDetail = components["schemas"]["ProjectDetail"];
export type CertificationDetail = components["schemas"]["CertificationDetail"];
export type EducationDetail = components["schemas"]["EducationDetail"];
export type SourceSummary = components["schemas"]["SourceSummary"];
export type SourceWrite =
  | components["schemas"]["RoleWrite"]
  | components["schemas"]["ProjectWrite"]
  | components["schemas"]["CertificationWrite"]
  | components["schemas"]["EducationWrite"];

export type BulletpointRecord = components["schemas"]["BulletpointRecord"];
export type WorklogSummary = components["schemas"]["WorklogSummary"];
export type WorklogWrite = components["schemas"]["WorklogWrite"];

/** Flat, string-valued form state; a checkbox drives the open-ended end date. */
export type SourceFormValues = Record<string, string>;

export type LoadStatus = "loading" | "ready" | "error";
