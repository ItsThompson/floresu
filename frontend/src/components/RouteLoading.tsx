/**
 * Neutral full-viewport loading state shown while the session resolves, so a
 * guarded route never flashes its content or misroutes before `status` settles.
 */
export function RouteLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-background text-muted-foreground flex min-h-svh items-center justify-center"
    >
      <span className="text-sm">Loading…</span>
    </div>
  );
}
