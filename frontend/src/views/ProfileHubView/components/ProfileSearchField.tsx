import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";

interface ProfileSearchFieldProps {
  /** Emits the submitted query; the hub routes it to the Library search. */
  onSearch: (query: string) => void;
}

/**
 * The hub's "search experience" field. It holds only the draft query and emits
 * the search intent on submit; the hub owns where it routes (the Library search),
 * so this component carries no navigation or business rule.
 */
export function ProfileSearchField({ onSearch }: ProfileSearchFieldProps) {
  const [query, setQuery] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed) onSearch(trimmed);
  };

  return (
    <form role="search" onSubmit={handleSubmit} className="flex items-center gap-2">
      <div className="border-input bg-card focus-within:border-ring focus-within:ring-ring/50 flex h-9 items-center gap-2 rounded-md border px-3 focus-within:ring-[3px]">
        <Search aria-hidden className="text-muted-foreground size-4" />
        <input
          type="search"
          aria-label="Search experience"
          placeholder="Search experience"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="placeholder:text-muted-foreground w-48 bg-transparent text-sm outline-none"
        />
      </div>
    </form>
  );
}
