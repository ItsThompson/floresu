/**
 * Shared async-state vocabulary for the write, load, and export lifecycles.
 *
 * Each union carries its error message inside the `error` arm only, so there is
 * no parallel `error` field that can survive a successful reload and go stale.
 * This makes the impossible pairs (e.g. `ready` next to a leftover error)
 * uncompilable rather than merely unlikely.
 */

/** Lifecycle of a single data fetch. `ready` covers the empty result too. */
export type LoadState =
  | { status: "loading" }
  | { status: "ready" }
  | { status: "error"; message: string };

/**
 * Lifecycle of a single mutating action (save, add, edit, finalize).
 * `stale` is the 409 / If-Match-conflict arm used by the optimistic-concurrency
 * hooks; hooks that never conflict simply never enter it.
 */
export type WriteState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "error"; message: string }
  | { status: "stale" };

/**
 * Export lifecycle. Standalone by design (not composed from `WriteState`) so it
 * can carry a payload-bearing `done` arm without inheriting `WriteState`'s
 * `stale` arm, which is meaningless for an export.
 */
export type ExportState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "error"; message: string }
  | { status: "done"; url: string };
