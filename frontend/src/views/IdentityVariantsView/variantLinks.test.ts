import { describe, expect, it } from "vitest";

import { linksToText, textToLinks } from "./variantLinks";

describe("variant links", () => {
  it("formats links as one 'label | url' line each", () => {
    expect(linksToText([{ label: "Portfolio", url: "https://a.dev" }])).toBe(
      "Portfolio | https://a.dev",
    );
  });

  it("parses labeled lines into typed links", () => {
    expect(textToLinks("Portfolio | https://a.dev\nGitHub | https://gh.dev")).toEqual([
      { label: "Portfolio", url: "https://a.dev" },
      { label: "GitHub", url: "https://gh.dev" },
    ]);
  });

  it("treats a separator-less line as a bare URL used as its own label", () => {
    expect(textToLinks("https://a.dev")).toEqual([{ label: "https://a.dev", url: "https://a.dev" }]);
  });

  it("drops blank lines and lines with no URL", () => {
    expect(textToLinks("\nPortfolio |   \n")).toEqual([]);
  });

  it("round-trips through text and back", () => {
    const links = [{ label: "Site", url: "https://s.dev" }];
    expect(textToLinks(linksToText(links))).toEqual(links);
  });
});
