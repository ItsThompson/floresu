import { Link } from "react-router";

import { Button } from "@/components/ui/button";

import { HEADER_SIGNED_IN_LABEL, START_LABEL, WORDMARK } from "../constants";
import { useStartDestination } from "../hooks/useStartDestination";

/**
 * The public page's chrome: the wordmark and one control. An authenticated
 * visitor sees this page too, so the control switches from signup to a way back
 * into the app. It stays empty while the session resolves, so the label never
 * flips in front of the visitor.
 */
export function LandingHeader() {
  const destination = useStartDestination();

  return (
    <header className="reading-width flex w-full items-center justify-between px-6 py-5">
      <span className="font-serif text-xl font-medium lowercase tracking-tight">{WORDMARK}</span>
      {destination && (
        <Button size="sm" asChild>
          <Link to={destination.path}>
            {destination.isSignedIn ? HEADER_SIGNED_IN_LABEL : START_LABEL}
          </Link>
        </Button>
      )}
    </header>
  );
}
