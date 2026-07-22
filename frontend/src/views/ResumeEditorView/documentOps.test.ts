import { describe, expect, it } from "vitest";

import { buildLibraryRefItem, buildLocalItem, buildResumeRecord, buildSection } from "@/mocks/resumeFixtures";

import { moveInOrder, orderedItems, toResumeUpdate, withLocalItemText } from "./documentOps";

describe("orderedItems", () => {
  it("resolves items in the explicit item_order, skipping missing ids", () => {
    const a = buildLocalItem({ id: "a", text: "A" });
    const b = buildLocalItem({ id: "b", text: "B" });
    const section = buildSection({
      item_order: ["b", "missing", "a"],
      items: { a, b },
    });
    expect(orderedItems(section).map((item) => item.id)).toEqual(["b", "a"]);
  });
});

describe("moveInOrder", () => {
  it("moves an id from one position to another", () => {
    expect(moveInOrder(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]);
    expect(moveInOrder(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
  });

  it("returns the same order for a no-op or out-of-range move", () => {
    expect(moveInOrder(["a", "b"], 1, 1)).toEqual(["a", "b"]);
    expect(moveInOrder(["a", "b"], 5, 0)).toEqual(["a", "b"]);
  });
});

describe("withLocalItemText", () => {
  it("replaces only the targeted local item's text", () => {
    const local = buildLocalItem({ id: "loc", text: "old" });
    const record = buildResumeRecord({
      document: {
        schema_version: 1,
        template_id: "classic",
        header: {},
        sections: [buildSection({ id: "s", item_order: ["loc"], items: { loc: local } })],
      },
    });
    const update = withLocalItemText(record, "loc", "new text");
    const section = update.sections?.[0];
    expect(section?.items?.loc).toMatchObject({ kind: "local", text: "new text" });
  });

  it("leaves a library_ref item untouched (its text is not edited here)", () => {
    const ref = buildLibraryRefItem({ id: "ref", bullet_id: 7 });
    const record = buildResumeRecord({
      document: {
        schema_version: 1,
        template_id: "classic",
        header: {},
        sections: [buildSection({ id: "s", item_order: ["ref"], items: { ref } })],
      },
    });
    const update = withLocalItemText(record, "ref", "ignored");
    expect(update.sections?.[0].items?.ref).toEqual(ref);
  });
});

describe("toResumeUpdate", () => {
  it("projects the record into a write body and applies overrides", () => {
    const record = buildResumeRecord({ title: "Original" });
    expect(toResumeUpdate(record)).toMatchObject({ title: "Original", template_id: "classic" });
    expect(toResumeUpdate(record, { template_id: "modern" }).template_id).toBe("modern");
  });
});
