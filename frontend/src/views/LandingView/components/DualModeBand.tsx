import {
  DUAL_MODE_FOOTNOTE,
  DUAL_MODE_HEADING,
  DUAL_MODE_NOTE,
  DUAL_MODE_TRACKS,
} from "../constants";
import { DualModeTrack } from "./DualModeTrack";

/** The differentiator: you write, or the agent you already use writes over MCP. */
export function DualModeBand() {
  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <h2 className="text-2xl font-semibold tracking-tight">{DUAL_MODE_HEADING}</h2>
        <p className="text-muted-foreground max-w-[62ch]">{DUAL_MODE_NOTE}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {DUAL_MODE_TRACKS.map((track) => (
          <DualModeTrack key={track.heading} track={track} />
        ))}
      </div>
      <p className="text-muted-foreground text-sm">{DUAL_MODE_FOOTNOTE}</p>
    </section>
  );
}
