// Typed calls to the Ludwig service (/api). The token, when the service needs one, is kept
// for this browser tab only.

export type Status = "fail" | "pass" | "not_checked" | "not_applicable";
export type Severity = "blocker" | "warning" | "info";

export interface SourceRef {
  file: string;
  kind: "ifc" | "sheet" | "dxf" | "pdf" | "erp";
  ifc_guid?: string;
  sheet?: string;
  cell?: string;
  dxf_handle?: string;
  layer?: string;
  page?: number;
  bbox?: [number, number, number, number];
}

export interface Review {
  decision: "accept" | "dismiss";
  reason: string;
  created: string;
}

export interface Finding {
  id: number;
  run_id: number;
  rule_id: string;
  pack: string;
  pack_version: string;
  status: Status;
  severity: Severity;
  element_ids: string[];
  mark: string | null;
  measured: unknown;
  expected: string | null;
  message: string;
  evidence: SourceRef[];
  reason: string | null;
  review: Review | null;
}

export interface FindingDetail extends Finding {
  reviews: Review[];
  files: Record<string, number>;
}

export interface Project {
  id: number;
  name: string;
  created: string;
}

export interface Upload {
  id: number;
  role: "architect" | "erp" | "mapping";
  filename: string;
  sha256: string;
  size: number;
  for_upload: number | null;
}

export interface Summary {
  rules_run: number;
  elements_total: number;
  elements_covered: number;
  not_checked: number;
  by_status: Record<string, number>;
  fails_by_severity: Record<string, number>;
  parse_warnings: number;
}

export interface Run {
  id: number;
  project_id: number;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  pack: { name: string; version: string; hash: string };
  summary: Summary | null;
  files: Record<string, number>;
  created: string;
  finished: string | null;
}

export interface Pack {
  name: string;
  version: string;
  hash: string;
  description: string;
  rules: number;
}

export interface Limit {
  path: string;
  value: number;
  line: number;
  note: string;
  used_by: string[];
}

export interface PackDetail extends Omit<Pack, "rules"> {
  writable: boolean;
  limits: Limit[];
  rules: { id: string; kind: string; severity: Severity; description: string; message: string }[];
  changes: { values: Record<string, number>; reason: string; created: string }[];
}

const TOKEN_KEY = "ludwig-token";

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

function headers(): Record<string, string> {
  const token = sessionStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { ...headers(), ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  packs: () => call<Pack[]>("/packs"),
  pack: (name: string) => call<PackDetail>(`/packs/${encodeURIComponent(name)}`),
  setLimits: (name: string, values: Record<string, number>, reason: string) =>
    call<PackDetail>(`/packs/${encodeURIComponent(name)}/limits`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values, reason }),
    }),
  projects: () => call<Project[]>("/projects"),
  project: (id: number) => call<Project>(`/projects/${id}`),
  createProject: (name: string) => call<Project>("/projects", json({ name })),
  uploads: (project: number) => call<Upload[]>(`/projects/${project}/uploads`),
  upload: (project: number, file: File, role: Upload["role"], forUpload?: number) => {
    const form = new FormData();
    form.append("file", file);
    form.append("role", role);
    if (forUpload !== undefined) form.append("for_upload", String(forUpload));
    return call<Upload>(`/projects/${project}/uploads`, { method: "POST", body: form });
  },
  runs: (project: number) => call<Run[]>(`/projects/${project}/runs`),
  startRun: (project: number, pack: string, uploads: number[]) =>
    call<Run>(`/projects/${project}/runs`, json({ pack, uploads })),
  run: (id: number) => call<Run>(`/runs/${id}`),
  findings: (run: number, status?: string) =>
    call<Finding[]>(`/runs/${run}/findings${status ? `?status=${status}` : ""}`),
  finding: (id: number) => call<FindingDetail>(`/findings/${id}`),
  review: (id: number, decision: Review["decision"], reason: string) =>
    call<Review>(`/findings/${id}/review`, json({ decision, reason })),
};

export interface Draft {
  text: string;
  problems: string[];
  note: string;
}

export const assist = {
  state: () => call<{ enabled: boolean }>("/assist"),
  explain: (finding: number) =>
    call<{ explanation: string; original: string; note: string }>(`/assist/explain/${finding}`, {
      method: "POST",
    }),
  rule: (pack: string, text: string) => call<Draft>("/assist/rule", json({ pack, text })),
};

export const reportUrl = (run: number, name: string) => `/api/runs/${run}/reports/${name}`;
export const csvUrl = (run: number) => `/api/runs/${run}/findings.csv`;
export const pageUrl = (upload: number, page: number) => `/api/uploads/${upload}/pages/${page}.png`;
export const PAGE_SCALE = 1.5;

// Files and images go through fetch so the token is sent; links cannot carry it.
export async function fetchBlob(url: string): Promise<Blob> {
  const response = await fetch(url, { headers: headers() });
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.blob();
}

export async function download(url: string, name: string): Promise<void> {
  const href = URL.createObjectURL(await fetchBlob(url));
  const link = document.createElement("a");
  link.href = href;
  link.download = name;
  link.click();
  URL.revokeObjectURL(href);
}
