import { Copy } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

/** Copy outcome. `unavailable` covers a missing or denied Clipboard API. */
type CopyStatus = "idle" | "copied" | "unavailable";

interface McpUrlFieldProps {
  url: string;
}

/**
 * A read-only MCP URL field with a copy control, shared by every surface that
 * shows the URL (onboarding and Settings). Copy is a best-effort convenience: if
 * the Clipboard API is missing or denied, the field is selected and a manual-copy
 * hint appears, so the user is never left without feedback and the button never
 * falsely claims success.
 */
export function McpUrlField({ url }: McpUrlFieldProps) {
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleCopy = async () => {
    if (!navigator.clipboard) {
      setCopyStatus("unavailable");
      inputRef.current?.select();
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("unavailable");
      inputRef.current?.select();
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          readOnly
          aria-label="MCP URL"
          value={url}
          className="border-input bg-muted h-9 flex-1 rounded-md border px-3 font-mono text-sm outline-none"
        />
        <Button variant="outline" onClick={() => void handleCopy()}>
          <Copy aria-hidden />
          {copyStatus === "copied" ? "Copied" : "Copy"}
        </Button>
      </div>
      {copyStatus === "unavailable" && (
        <p role="status" className="text-muted-foreground text-sm">
          Couldn&apos;t copy automatically. The URL above is selected: copy it manually.
        </p>
      )}
    </div>
  );
}
