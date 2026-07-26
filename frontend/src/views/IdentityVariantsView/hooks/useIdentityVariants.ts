import { useCallback, useEffect, useState } from "react";

import type { components } from "@/api";
import { useSessionClient } from "@/api";
import { extractProblem } from "@/lib/problemDetail";

export type IdentityVariantRead = components["schemas"]["IdentityVariantRead"];
export type IdentityVariantWrite = components["schemas"]["IdentityVariantWrite"];

/** The rule a referenced-variant archive raises, so the hook can drive the replacement prompt. */
export const REPLACEMENT_REQUIRED_RULE = "identity_variant_replacement_required";

export type VariantsStatus = "loading" | "ready" | "error";

/** Data for the replacement prompt shown when a referenced variant is archived. */
export interface ReplacementPrompt {
  variantId: number;
  resumeIds: string[];
  message: string;
}

export interface VariantsState {
  status: VariantsStatus;
  variants: IdentityVariantRead[];
  actionError: string | null;
  replacementPrompt: ReplacementPrompt | null;
}

export interface VariantsActions {
  create: (write: IdentityVariantWrite) => Promise<boolean>;
  update: (id: number, write: IdentityVariantWrite) => Promise<boolean>;
  setDefault: (id: number) => void;
  archive: (id: number) => void;
  archiveWithReplacement: (replacementId: number) => void;
  dismissError: () => void;
  dismissReplacementPrompt: () => void;
}

/**
 * Owns the identity variants and their mutations. The exactly-one-default and
 * archive-block rules are enforced by the backend; this hook surfaces their
 * outcomes. Archiving a variant a living resume references returns a structured
 * replacement-required violation, which becomes the replacement prompt the view
 * renders; confirming it posts the chosen replacement so the backend re-points the
 * referencing resumes and archives the original atomically. Create/update resolve
 * to a boolean so the form can close only on a committed write.
 */
export function useIdentityVariants(): { state: VariantsState; actions: VariantsActions } {
  const client = useSessionClient();
  const [status, setStatus] = useState<VariantsStatus>("loading");
  const [variants, setVariants] = useState<IdentityVariantRead[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [replacementPrompt, setReplacementPrompt] = useState<ReplacementPrompt | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setStatus("loading");
    void client
      .GET("/identity-variants")
      .then(({ data }) => {
        if (!active) return;
        if (!data) {
          setStatus("error");
          return;
        }
        setVariants(data);
        setStatus("ready");
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [client, reloadToken]);

  const refetch = useCallback(() => setReloadToken((token) => token + 1), []);

  const create = useCallback(
    async (write: IdentityVariantWrite): Promise<boolean> => {
      setActionError(null);
      try {
        const { data, error } = await client.POST("/identity-variants", { body: write });
        if (error || !data) {
          setActionError(extractProblem(error).message);
          return false;
        }
        // A create can flip the previous default, so refetch for the whole set.
        refetch();
        return true;
      } catch {
        setActionError("Could not create that variant.");
        return false;
      }
    },
    [client, refetch],
  );

  const update = useCallback(
    async (id: number, write: IdentityVariantWrite): Promise<boolean> => {
      setActionError(null);
      try {
        const { data, error } = await client.PUT("/identity-variants/{variant_id}", {
          params: { path: { variant_id: id } },
          body: write,
        });
        if (error || !data) {
          setActionError(extractProblem(error).message);
          return false;
        }
        refetch();
        return true;
      } catch {
        setActionError("Could not update that variant.");
        return false;
      }
    },
    [client, refetch],
  );

  const setDefault = useCallback(
    (id: number) => {
      const variant = variants.find((candidate) => candidate.id === id);
      if (!variant || variant.is_default) return;
      void update(id, toWrite(variant, true));
    },
    [variants, update],
  );

  const archive = useCallback(
    (id: number) => {
      setActionError(null);
      void client
        .POST("/identity-variants/{variant_id}/archive", { params: { path: { variant_id: id } } })
        .then(({ error }) => {
          if (!error) {
            setVariants((current) => current.filter((variant) => variant.id !== id));
            return;
          }
          const problem = extractProblem(error);
          const violation = problem.violations.find((v) => v.rule === REPLACEMENT_REQUIRED_RULE);
          if (violation) {
            setReplacementPrompt({ variantId: id, resumeIds: violation.ids, message: problem.message });
          } else {
            setActionError(problem.message);
          }
        })
        .catch(() => setActionError("Could not archive that variant."));
    },
    [client],
  );

  const dismissError = useCallback(() => setActionError(null), []);
  const dismissReplacementPrompt = useCallback(() => setReplacementPrompt(null), []);

  const archiveWithReplacement = useCallback(
    (replacementId: number) => {
      if (!replacementPrompt) return;
      const id = replacementPrompt.variantId;
      setActionError(null);
      void client
        .POST("/identity-variants/{variant_id}/archive", {
          params: { path: { variant_id: id } },
          body: { replacement_variant_id: replacementId },
        })
        .then(({ error }) => {
          setReplacementPrompt(null);
          if (error) {
            setActionError(extractProblem(error).message);
            return;
          }
          setVariants((current) => current.filter((variant) => variant.id !== id));
        })
        .catch(() => {
          setReplacementPrompt(null);
          setActionError("Could not archive that variant.");
        });
    },
    [client, replacementPrompt],
  );

  return {
    state: { status, variants, actionError, replacementPrompt },
    actions: {
      create,
      update,
      setDefault,
      archive,
      archiveWithReplacement,
      dismissError,
      dismissReplacementPrompt,
    },
  };
}

/** Build a full-representation write body from a read, overriding the default flag. */
export function toWrite(variant: IdentityVariantRead, isDefault: boolean): IdentityVariantWrite {
  return {
    label: variant.label,
    full_name: variant.full_name,
    contact: variant.contact,
    links: variant.links,
    is_default: isDefault,
  };
}
