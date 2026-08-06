import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";

import { EMPTY_SEARCH_MESSAGE } from "./constants";
import { SearchResults } from "./SearchResults";
import type { SearchResult } from "./rankedRows";

const EMPTY_RESULT: SearchResult = {
  ranked: [],
  graph: { sources: [], worklog: [], bullets: [] },
  notices: [],
};

const RESULT: SearchResult = {
  ranked: [
    { type: "source", id: 1, score: 0.9 },
    { type: "bullet", id: 20, score: 0.7 },
    { type: "worklog", id: 30, score: 0.5 },
    { type: "worklog", id: 31, score: 0.4 },
  ],
  graph: {
    sources: [
      { id: 1, kind: "role", label: "Acme Senior Engineer", match_score: 0.9, score: 0.95 },
    ],
    worklog: [
      { id: 30, title: "Shipped payments", date: "2026-07-18", score: 0.5, source_ids: [1] },
      { id: 31, title: "Unattached research note", date: "2026-07-10", score: 0.4, source_ids: [] },
    ],
    bullets: [
      { id: 20, text: "Cut checkout latency 40%", score: 0.7, worklog_ids: [30], source_ids: [] },
    ],
  },
  notices: [],
};

describe("SearchResults", () => {
  it("shows the empty message when nothing ranked", () => {
    renderWithProviders(<SearchResults result={EMPTY_RESULT} />);

    expect(screen.getByText(EMPTY_SEARCH_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Top matches" })).not.toBeInTheDocument();
  });

  it("links bullet and source hits to where they live and leaves worklog hits as text", () => {
    renderWithProviders(<SearchResults result={RESULT} />);

    const topMatches = screen.getByRole("region", { name: "Top matches" });
    expect(
      within(topMatches).getByRole("link", { name: "Cut checkout latency 40%" }),
    ).toHaveAttribute("href", "/library?bullet=20");
    expect(within(topMatches).getByRole("link", { name: "Acme Senior Engineer" })).toHaveAttribute(
      "href",
      "/profile/sources/1",
    );
    // A worklog hit is already on the page it would link from, so it stays text.
    expect(within(topMatches).getByText("Unattached research note")).toBeInTheDocument();
    expect(
      within(topMatches).queryByRole("link", { name: "Unattached research note" }),
    ).not.toBeInTheDocument();
  });

  it("groups the same hits under their source, reachable through the worklog chain", () => {
    renderWithProviders(<SearchResults result={RESULT} />);

    const grouped = screen.getByRole("region", { name: "Grouped by source" });
    expect(
      within(grouped).getByRole("heading", { name: /Acme Senior Engineer/ }),
    ).toBeInTheDocument();
    expect(within(grouped).getByText("Role")).toBeInTheDocument();
    expect(within(grouped).getByText("matched directly")).toBeInTheDocument();
    expect(within(grouped).getByText("Shipped payments")).toBeInTheDocument();
    // Bullet 20 links to worklog 30, not to the source directly, yet rolls up here.
    expect(within(grouped).getByText("Cut checkout latency 40%")).toBeInTheDocument();
    // The unattached worklog hit has no source, so the grouped view omits it.
    expect(within(grouped).queryByText("Unattached research note")).not.toBeInTheDocument();
  });

  it("prints a secondary detail beside each ranked hit, so an unattached worklog keeps its date", () => {
    renderWithProviders(<SearchResults result={RESULT} />);

    const topMatches = screen.getByRole("region", { name: "Top matches" });
    const [sourceRow, bulletRow, , unattachedRow] = within(topMatches).getAllByRole("listitem");

    expect(within(sourceRow).getByText("Role")).toBeInTheDocument();
    // The ranked list is the only place a source-less worklog hit appears, so its
    // date has to travel with it.
    expect(within(unattachedRow).getByText("Jul 10")).toHaveAttribute("dateTime", "2026-07-10");
    // A bullet's statement is its own label; nothing is appended.
    expect(bulletRow).toHaveTextContent(/^BulletCut checkout latency 40%$/);
  });

  it("reads a worklog date the same way in the ranked list and in its source group", () => {
    renderWithProviders(<SearchResults result={RESULT} />);

    const ranked = within(screen.getByRole("region", { name: "Top matches" })).getByText("Jul 18");
    const grouped = within(screen.getByRole("region", { name: "Grouped by source" })).getByText(
      "Jul 18",
    );

    expect(ranked).toHaveAttribute("dateTime", "2026-07-18");
    expect(grouped).toHaveAttribute("dateTime", "2026-07-18");
  });

  it("surfaces a soft notice above the results rather than failing the query", () => {
    renderWithProviders(
      <SearchResults
        result={{
          ...RESULT,
          notices: [{ code: "semantic_degraded", message: "Lexical results only." }],
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Lexical results only.");
    expect(screen.getByRole("region", { name: "Top matches" })).toBeInTheDocument();
  });
});
