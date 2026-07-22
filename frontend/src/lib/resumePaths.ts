/** The resumes list route. */
export const RESUMES_PATH = "/resumes";

/** The route pattern the editor route is registered under. */
export const RESUME_EDITOR_PATH_PATTERN = "/resumes/:resumeId";

/** The editor route for one resume. */
export function resumeEditorPath(id: number): string {
  return `/resumes/${id}`;
}
