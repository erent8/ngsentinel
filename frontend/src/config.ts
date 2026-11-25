/** Build-time configuration. VITE_STATIC=1 builds a read-only showcase that reads
 * pre-exported analysis results from ./data instead of calling the API. */
export const STATIC = import.meta.env.VITE_STATIC === "1";
export const REPO_URL: string = import.meta.env.VITE_REPO_URL ?? "";
export const LIVE_URL: string = import.meta.env.VITE_LIVE_URL ?? "";
