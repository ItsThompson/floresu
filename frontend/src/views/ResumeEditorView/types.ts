import type { components } from "@/api";

export type ResumeRecord = components["schemas"]["ResumeRecord"];
export type ResumeSection = components["schemas"]["ResumeSection"];
export type LibraryRefItem = components["schemas"]["LibraryRefItem"];
export type LocalItem = components["schemas"]["LocalItem"];
export type ResumeItem = LibraryRefItem | LocalItem;
export type BulletpointRecord = components["schemas"]["BulletpointRecord"];
export type TemplateInfo = components["schemas"]["TemplateInfo"];
export type IdentityVariant = components["schemas"]["IdentityVariantRead"];
export type ResumeEditScope = components["schemas"]["ResumeEditScope"];
export type ResumeUpdate = components["schemas"]["ResumeUpdate"];

/** The editor load lifecycle. */
export type EditorStatus = "loading" | "ready" | "error";

/**
 * A pending shared-bullet edit awaiting a scope choice. Set only when the backend
 * responds `prompt` (the bullet is used in two or more resumes); the view renders
 * the dialog and sends the chosen scope back with the same edit.
 */
export interface ScopePromptContext {
  bulletId: number;
  newText: string;
  usedInCount: number;
}

export interface ResumeEditorState {
  status: EditorStatus;
  record: ResumeRecord | null;
  /** Canonical bullets referenced by the document, keyed by id (text + used-in count). */
  bullets: Record<number, BulletpointRecord>;
  variants: IdentityVariant[];
  templates: TemplateInfo[];
  /** Load error (the resume could not be fetched). */
  error: string | null;
  /** Inline write error, preserved for retry (never a false success). */
  saveError: string | null;
  /** A write was rejected as stale (409); the view prompts to re-read. */
  isStale: boolean;
  /** A shared-bullet edit awaiting a scope choice, or null. */
  scopePrompt: ScopePromptContext | null;
  /** Finalized resumes are read-only (fork to edit). */
  isReadOnly: boolean;
  /** Changes on every successful write so the debounced preview re-fetches. */
  previewKey: number;
}

export interface ResumeEditorActions {
  /** Re-read the resume from the server (recovers from a stale-write conflict). */
  reload: () => void;
  dismissStale: () => void;
  /** Edit an item's text: a local item saves directly; a library_ref runs the scope flow. */
  editItemText: (item: ResumeItem, newText: string) => void;
  /** Apply the pending shared-bullet edit with the chosen scope. */
  resolveScope: (scope: ResumeEditScope) => void;
  cancelScope: () => void;
  addLibraryItem: (sectionId: string, bulletId: number) => void;
  addInlineItem: (sectionId: string, text: string) => void;
  removeItem: (itemId: string) => void;
  reorderSections: (orderedSectionIds: string[]) => void;
  reorderItems: (sectionId: string, orderedItemIds: string[]) => void;
  setTemplate: (templateId: string) => void;
  setTitle: (title: string) => void;
  setIdentityVariant: (variantId: number | null) => void;
  /** Promote a local item to a canonical, searchable library bullet. */
  promoteItem: (itemId: string) => void;
  /** Render and persist a PDF; resolves to a download URL, or null on failure. */
  exportPdf: () => Promise<string | null>;
}

export interface ResumeEditor {
  state: ResumeEditorState;
  actions: ResumeEditorActions;
}
