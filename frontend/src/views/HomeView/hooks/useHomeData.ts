import { useEffect, useState } from "react";

import { useSessionClient } from "@/api";

import { WORKLOG_PREVIEW_COUNT } from "../constants";
import { selectRecentWorklog } from "../recentWorklog";
import type { HomeData, HomeSection, ResumeSummary, WorklogSummary } from "../types";

/**
 * Loads Home's two data-backed regions from the existing list reads. The two
 * fetches run in parallel and each settles its own section, so one failed read
 * shows that section's error while the other still renders (the independence
 * rule): neither waits on nor blanks the other.
 *
 * The worklog list is sorted newest-first and capped to the preview count here,
 * so the sections stay purely presentational.
 */
export function useHomeData(): HomeData {
  const client = useSessionClient();
  const [worklog, setWorklog] = useState<HomeSection<WorklogSummary>>({
    items: [],
    status: "loading",
  });
  const [resumes, setResumes] = useState<HomeSection<ResumeSummary>>({
    items: [],
    status: "loading",
  });

  useEffect(() => {
    let cancelled = false;

    client
      .GET("/worklog")
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error || !data) setWorklog({ items: [], status: "error" });
        else setWorklog({ items: selectRecentWorklog(data, WORKLOG_PREVIEW_COUNT), status: "ready" });
      })
      .catch(() => {
        if (!cancelled) setWorklog({ items: [], status: "error" });
      });

    client
      .GET("/resumes")
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error || !data) setResumes({ items: [], status: "error" });
        else setResumes({ items: data, status: "ready" });
      })
      .catch(() => {
        if (!cancelled) setResumes({ items: [], status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [client]);

  return { worklog, resumes };
}
