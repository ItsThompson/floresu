import { useCallback, useEffect, useState } from "react";

import type { components } from "@/api";
import { useSessionClient } from "@/api";
import { extractProblem } from "@/lib/problemDetail";
import { reorderBySortOrder } from "@/lib/reorder";

export type SkillRead = components["schemas"]["SkillRead"];

export type SkillsStatus = "loading" | "ready" | "error";

export interface SkillsState {
  status: SkillsStatus;
  skills: SkillRead[];
  actionError: string | null;
}

export interface SkillsActions {
  create: (name: string) => void;
  rename: (id: number, name: string) => void;
  reorder: (orderedIds: number[]) => void;
  archive: (id: number) => void;
  dismissError: () => void;
}

/**
 * Owns the curated skills list and its mutations: add, rename, reorder, archive.
 * Reorder and archive apply optimistically then confirm; a failure surfaces a
 * banner and refetches. A tag is never promoted to a skill here: skills are added
 * only through the explicit create action, so curation stays deliberate. Usage
 * counts are read straight from the backend (derived, not stored).
 */
export function useSkills(): { state: SkillsState; actions: SkillsActions } {
  const client = useSessionClient();
  const [status, setStatus] = useState<SkillsStatus>("loading");
  const [skills, setSkills] = useState<SkillRead[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setStatus("loading");
    void client
      .GET("/skills")
      .then(({ data }) => {
        if (!active) return;
        if (!data) {
          setStatus("error");
          return;
        }
        setSkills([...data].sort((left, right) => left.sort_order - right.sort_order));
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
  const fail = useCallback(
    (error: unknown, fallback: string) => {
      setActionError(error ? extractProblem(error).message : fallback);
      refetch();
    },
    [refetch],
  );

  const create = useCallback(
    (name: string) => {
      if (!name.trim()) return;
      setActionError(null);
      void client
        .POST("/skills", { body: { name: name.trim() } })
        .then(({ data, error }) => {
          if (error || !data) setActionError(extractProblem(error).message);
          else setSkills((current) => [...current, data]);
        })
        .catch(() => setActionError("Could not add that skill."));
    },
    [client],
  );

  const rename = useCallback(
    (id: number, name: string) => {
      if (!name.trim()) return;
      setActionError(null);
      void client
        .PUT("/skills/{skill_id}", { params: { path: { skill_id: id } }, body: { name: name.trim() } })
        .then(({ data, error }) => {
          if (error || !data) setActionError(extractProblem(error).message);
          else setSkills((current) => current.map((skill) => (skill.id === id ? data : skill)));
        })
        .catch(() => setActionError("Could not rename that skill."));
    },
    [client],
  );

  const reorder = useCallback(
    (orderedIds: number[]) => {
      setSkills((current) => reorderBySortOrder(current, orderedIds));
      void client
        .POST("/skills/reorder", { body: { skill_ids: orderedIds } })
        .then(({ error }) => {
          if (error) fail(error, "Could not save the new order.");
        })
        .catch(() => fail(null, "Could not save the new order."));
    },
    [client, fail],
  );

  const archive = useCallback(
    (id: number) => {
      setSkills((current) => current.filter((skill) => skill.id !== id));
      void client
        .POST("/skills/{skill_id}/archive", { params: { path: { skill_id: id } } })
        .then(({ error }) => {
          if (error) fail(error, "Could not archive that skill.");
        })
        .catch(() => fail(null, "Could not archive that skill."));
    },
    [client, fail],
  );

  const dismissError = useCallback(() => setActionError(null), []);

  return {
    state: { status, skills, actionError },
    actions: { create, rename, reorder, archive, dismissError },
  };
}
