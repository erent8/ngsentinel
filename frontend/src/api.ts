import { STATIC } from "./config";
import type { Metrics, RulesResponse, RunDetail, RunRecord, ToolInfo } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const body = await r.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface InputFile {
  path: string;
  name: string;
  size_bytes: number;
}

export interface ServerConfig {
  public: boolean;
  max_upload_mb: number;
  run_ttl_hours: number;
}

const READ_ONLY = "This is a read-only showcase. Install NGSentinel (see the project page) to run your own analyses.";
const sget = <T,>(path: string) => fetch(`./data/${path}`).then((r) => {
  if (!r.ok) throw new ApiError(r.status, `could not load ${path}`);
  return r.json() as Promise<T>;
});
const denied = (): Promise<never> => Promise.reject(new ApiError(403, READ_ONLY));

/** Read-only API backed by exported JSON files (VITE_STATIC builds). */
const staticApi = {
  config: () => Promise.resolve<ServerConfig>({ public: true, max_upload_mb: 0, run_ttl_hours: 0 }),
  runs: () => sget<RunRecord[]>("runs.json"),
  run: (id: string) => sget<RunDetail>(`runs/${id}/detail.json`),
  metrics: (id: string, which: "raw" | "processed") => sget<Metrics>(`runs/${id}/metrics_${which}.json`),
  deleteRun: (_id: string) => denied(),
  startRun: (_body: unknown) => denied(),
  tools: (_refresh = false) => sget<Record<string, ToolInfo>>("tools.json"),
  rules: () => sget<RulesResponse>("rules.json"),
  saveRules: (_text: string) => denied(),
  resetRules: () => denied(),
  demoData: (_pairs = 20000) => denied(),
  checkPath: (_path: string) => denied(),
  upload: (_file: File, _onProgress?: (p: number) => void) => denied(),
  fileUrl: (id: string, path: string) => `./data/runs/${id}/files/${path}`,
};

const liveApi = {
  config: () => req<ServerConfig>("/api/config"),
  runs: () => req<RunRecord[]>("/api/runs"),
  run: (id: string) => req<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  metrics: (id: string, which: "raw" | "processed") => req<Metrics>(`/api/runs/${encodeURIComponent(id)}/metrics/${which}`),
  deleteRun: (id: string) => req<{ deleted: string }>(`/api/runs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  startRun: (body: unknown) => req<{ run_id: string }>("/api/runs", json("POST", body)),
  tools: (refresh = false) => req<Record<string, ToolInfo>>(`/api/tools${refresh ? "?refresh=true" : ""}`),
  rules: () => req<RulesResponse>("/api/rules"),
  saveRules: (text: string) => req<RulesResponse>("/api/rules", json("PUT", { text })),
  resetRules: () => req<RulesResponse>("/api/rules", { method: "DELETE" }),
  demoData: (pairs = 20000) => req<{ r1: string; r2: string; pairs: number; note: string }>(`/api/demo-data?pairs=${pairs}`, { method: "POST" }),
  checkPath: (path: string) => req<InputFile>("/api/inputs/check", json("POST", { path })),
  upload: (file: File, onProgress?: (p: number) => void) =>
    new Promise<InputFile>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const fd = new FormData();
      fd.append("file", file);
      xhr.open("POST", "/api/uploads");
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
        else {
          let msg = xhr.statusText;
          try {
            msg = JSON.parse(xhr.responseText).detail;
          } catch {
            /* ignore */
          }
          reject(new ApiError(xhr.status, msg));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, "network error"));
      xhr.send(fd);
    }),
  fileUrl: (id: string, path: string) => `/api/runs/${encodeURIComponent(id)}/files/${path}`,
};

export const api: typeof liveApi = STATIC ? (staticApi as unknown as typeof liveApi) : liveApi;

export const fmtInt = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("en-US"));
export const fmtNum = (n: number | null | undefined, d = 2) => (n == null ? "—" : n.toFixed(d));
export const fmtBytes = (n: number) => {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i ? 1 : 0)} ${u[i]}`;
};
export const fmtDate = (s: string | null | undefined) => (s ? new Date(s).toLocaleString() : "—");
