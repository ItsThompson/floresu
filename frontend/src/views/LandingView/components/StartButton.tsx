import { ArrowRight } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";

import { START_LABEL } from "../constants";
import { useStartDestination } from "../hooks/useStartDestination";

/**
 * The page's one primary call to action, rendered in the hero and again in the
 * closing band. While the session is still resolving it renders disabled rather
 * than as a link, so a returning visitor is never sent through signup.
 */
export function StartButton() {
  const destination = useStartDestination();

  if (destination === null) {
    return (
      <Button size="lg" disabled>
        {START_LABEL}
        <ArrowRight />
      </Button>
    );
  }

  return (
    <Button size="lg" asChild>
      <Link to={destination.path}>
        {START_LABEL}
        <ArrowRight />
      </Link>
    </Button>
  );
}
