import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { RequireOnboarded } from "@/components/RequireOnboarded";
import { buildFeedEvent } from "@/mocks/data";
import { routeComponents } from "@/test/routeComponents";

import { HomeView } from "./HomeView";
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

describe("entityHref produces in-app routes", () => {
  const producedHrefs = [...KNOWN_ENTITY_HREFS.map(([, href]) => href), ENTITY_HREF_FALLBACK];

  it.each(producedHrefs)("%s resolves to a route inside the app shell", (href) => {
    // Existence is not enough: a feed row is clicked by a signed-in user, so its
    // target has to resolve INSIDE the app. The public page at "/" matches a route
    // too, which is how a fallback aimed there would pass a weaker assertion while
    // ejecting the user out of the app.
    expect(routeComponents(href)).toContain(AppShell);
  });

  it("degrades an unknown entity_type to the in-app Home, not the public page", () => {
    expect(routeComponents(ENTITY_HREF_FALLBACK)).toEqual([
      RequireAuth,
      RequireOnboarded,
      AppShell,
      HomeView,
    ]);
  });
});
