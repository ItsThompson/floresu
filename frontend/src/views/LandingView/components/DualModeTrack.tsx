import type { DualModeTrackData } from "../types";

interface DualModeTrackProps {
  track: DualModeTrackData;
}

/** One track: who is doing the writing, and what that looks like in practice. */
export function DualModeTrack({ track }: DualModeTrackProps) {
  const { icon: Icon, heading, body } = track;

  return (
    <div className="bg-card text-card-foreground flex flex-col gap-3 rounded-lg border p-6">
      <div className="flex items-center gap-3">
        <span className="bg-accent text-accent-foreground flex size-9 items-center justify-center rounded-full">
          <Icon aria-hidden className="size-4" />
        </span>
        <h3 className="font-semibold">{heading}</h3>
      </div>
      <p className="text-muted-foreground text-sm">{body}</p>
    </div>
  );
}
