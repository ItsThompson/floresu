import { matchRoutes } from "react-router";
import { describe, expect, it } from "vitest";

import { buildFeedEvent } from "@/mocks/data";
import { appRoutes } from "@/routes";

import { ENTITY_HREF_FALLBACK, entityHref } from "./constants";

/** A fixed entity id so detail routes carry a concrete, matchable value. */
const ENTITY_ID = 6;

/** One case per known entity_type, with the route `entityHref` must produce. */
const KNOWN_ENTITY_HREFS: ReadonlyArray<readonly [entityType: string, expectedHref: string]> = [
  ["resume", `/resumes/${ENTITY_ID}`],
  ["bullet", `/library?bullet=${ENTITY_ID}`],
  ["source", `/profile/sources/${ENTITY_ID}`],
  ["worklog", "/worklog"],
  ["job_application", "/applications"],
  ["identity_variant", "/profile/identities"],
  ["skill", "/profile/skills"],
];

describe("entityHref", () => {
  it.each(KNOWN_ENTITY_HREFS)("maps a %s event to %s", (entityType, expectedHref) => {
    const href = entityHref(buildFeedEvent({ entity_type: entityType, entity_id: ENTITY_ID }));
    expect(href).toBe(expectedHref);
  });

  it("degrades an unknown entity_type to the safe fallback route", () => {
    const href = entityHref(buildFeedEvent({ entity_type: "mystery", entity_id: ENTITY_ID }));
    expect(href).toBe(ENTITY_HREF_FALLBACK);
  });
});

describe("entityHref produces routes that exist", () => {
  const producedHrefs = [...KNOWN_ENTITY_HREFS.map(([, href]) => href), ENTITY_HREF_FALLBACK];

  it.each(producedHrefs)("%s matches a route defined in routes.tsx", (href) => {
    expect(matchRoutes(appRoutes, href)).not.toBeNull();
  });
});
