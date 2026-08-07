import { isValidElement, type ReactElement } from "react";
import { matchRoutes } from "react-router";

import { appRoutes } from "@/routes";

/**
 * The components a URL renders, outermost layout route first, so a test can
 * assert both the destination view AND the guards it sits behind without
 * mounting anything. Empty when the URL matches no route. A route that declares
 * no element contributes `undefined`, which keeps its position in the chain
 * visible rather than dropping it.
 */
export function routeComponents(url: string): (ReactElement["type"] | undefined)[] {
  const matches = matchRoutes(appRoutes, url) ?? [];
  return matches.map((match) =>
    isValidElement(match.route.element) ? match.route.element.type : undefined,
  );
}
