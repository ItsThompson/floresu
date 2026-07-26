import type { components } from "@/api";

/** One activity-feed event: the audit-log row shape the feed and history share. */
export type FeedEvent = components["schemas"]["AuditEntry"];

/** A worklog timeline row: the recent-worklog preview item on Home. */
export type WorklogSummary = components["schemas"]["WorklogSummary"];

/** A resume list-projection row: the my-resumes item on Home. */
export type ResumeSummary = components["schemas"]["ResumeSummary"];

/** A Home content section's load lifecycle. `ready` covers the empty section too. */
export type HomeSectionStatus = "loading" | "ready" | "error";

/**
 * One Home content region's view model: its items beside its own status, so a
 * failed read blanks only that region and never its sibling section.
 */
export interface HomeSection<T> {
  items: T[];
  status: HomeSectionStatus;
}

/** Home's two data-backed regions, each loaded and statused independently. */
export interface HomeData {
  /** Newest-first, capped to the Home preview count. */
  worklog: HomeSection<WorklogSummary>;
  /** The account's resumes; each row links to its editor. */
  resumes: HomeSection<ResumeSummary>;
}

/** The feed's load lifecycle. `ready` covers the empty feed too. */
export type FeedStatus = "loading" | "ready" | "error";

export interface ActivityFeedState {
  status: FeedStatus;
  /** Events newest-first, deduped by id across the initial load and the stream. */
  events: FeedEvent[];
  error: string | null;
}

/**
 * The live SSE connection, abstracted behind a tiny interface so the hook is
 * testable without a real `EventSource` (absent under jsdom). The browser's
 * `EventSource` handles auto-reconnect and resends `Last-Event-ID` itself, so the
 * connection exposes only message/error subscription and close.
 */
export interface FeedConnection {
  onMessage(listener: (data: string) => void): void;
  onError(listener: () => void): void;
  close(): void;
}

export type CreateFeedConnection = () => FeedConnection;
export type LoadFeedHistory = () => Promise<FeedEvent[]>;

export interface UseActivityFeedParams {
  /** Load the initial recent rows (the durable audit record) before streaming. */
  loadHistory: LoadFeedHistory;
  /** Open the live stream; called only after the initial rows are in. */
  createConnection: CreateFeedConnection;
}
