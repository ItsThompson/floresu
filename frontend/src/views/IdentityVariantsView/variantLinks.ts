import type { components } from "@/api";

type VariantLink = components["schemas"]["VariantLink"];

/**
 * Identity-variant links are edited as one "Label | https://url" pair per line.
 * These convert between that text form and the typed `VariantLink[]` the API
 * carries. A line with no separator is treated as a bare URL used as its own
 * label; a line with no URL is dropped.
 */

export function linksToText(links: VariantLink[]): string {
  return links.map((link) => `${link.label} | ${link.url}`).join("\n");
}

export function textToLinks(text: string): VariantLink[] {
  return text.split("\n").flatMap((line) => {
    const trimmed = line.trim();
    if (!trimmed) return [];
    const separator = trimmed.indexOf("|");
    if (separator === -1) return [{ label: trimmed, url: trimmed }];
    const label = trimmed.slice(0, separator).trim();
    const url = trimmed.slice(separator + 1).trim();
    if (!url) return [];
    return [{ label: label || url, url }];
  });
}
