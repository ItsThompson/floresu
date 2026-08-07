/** The usage count text: "Unused" at zero, otherwise "Used in N". */
export function usedInLabel(count: number): string {
  return count === 0 ? "Unused" : `Used in ${count}`;
}

/** A bullet is shared (the row marks it) once two or more resumes reference it. */
export function isShared(count: number): boolean {
  return count >= 2;
}
