// API helpers for the Ludwig local daemon.
// Base URL comes from NEXT_PUBLIC_LUDWIG_API, defaulting to the local daemon.

export const API_BASE =
  process.env.NEXT_PUBLIC_LUDWIG_API?.replace(/\/$/, "") ||
  "http://localhost:8765";

// ---- daemon response shapes -------------------------------------------------

export interface Health {
  status: string;
  version?: string;
  blender?: string | null;
  blender_found?: boolean;
  provider?: string | null;
}

export interface ProjectSummary {
  id: string;
  slug: string;
  brief: string;
  created_at: number;
}

export interface Artifact {
  id: string;
  run_id: string;
  kind: string; // "code" | "render" | "hero" | "preview"
  path: string;
  created_at: number;
}

export interface Run {
  id: string;
  project_id: string;
  mode: string;
  params: Record<string, unknown>;
  status: string; // "running" | "done" | "error"
  score: number | null;
  critique: string | null;
  error?: string | null;
  created_at: number;
  finished_at?: number | null;
  artifacts: Artifact[];
}

export interface ProjectDetail extends ProjectSummary {
  runs: Run[];
}

// ---- discovery (the mandatory pre-generation brief lock) --------------------

export interface DiscoveryField {
  name: string;
  label: string;
  type: "select" | "text";
  options?: string[];
  default: string;
  help: string;
}

export interface DiscoverySchema {
  schema: DiscoveryField[];
  required: string[];
}

export type DiscoveryValues = Record<string, string>;

// ---- stream event shapes ----------------------------------------------------

export type StreamEvent =
  | { type: "start"; project_id: string; run_id: string; brief: string }
  | { type: "round"; round: number; rounds: number; candidates: number }
  | { type: "candidate"; label: string; score: number }
  | { type: "best"; score: number; path?: string }
  | { type: "hero_start" }
  | { type: "hero"; path: string }
  | { type: "cleared" }
  | { type: "log"; message: string }
  | {
      type: "done";
      project_id: string;
      run_id: string;
      score: number | null;
      critique: string | null;
      artifacts: {
        code?: string;
        render?: string;
        hero?: string;
        preview?: string;
      };
    }
  | { type: "error"; message: string };

export interface GenerateBody {
  brief: string;
  quick?: boolean;
  candidates?: number;
  rounds?: number;
  target?: number;
  workers?: number;
  discovery?: DiscoveryValues;
}

// Raised when the daemon rejects a generation because the brief lock is invalid.
export class DiscoveryError extends Error {
  problems: string[];
  constructor(message: string, problems: string[]) {
    super(message);
    this.name = "DiscoveryError";
    this.problems = problems;
  }
}

// ---- fetch helpers ----------------------------------------------------------

export function artifactUrl(id: string): string {
  return `${API_BASE}/api/artifacts/${id}/file`;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export function getHealth(): Promise<Health> {
  return getJson<Health>("/api/health");
}

export function listProjects(): Promise<{ projects: ProjectSummary[] }> {
  return getJson<{ projects: ProjectSummary[] }>("/api/projects");
}

export function getProject(id: string): Promise<ProjectDetail> {
  return getJson<ProjectDetail>(`/api/projects/${id}`);
}

export function getDiscoverySchema(): Promise<DiscoverySchema> {
  return getJson<DiscoverySchema>("/api/discovery/schema");
}

// Stream a generation run. EventSource cannot POST, so we use fetch + a reader
// and parse SSE frames manually. Each parsed event is handed to `onEvent`.
export async function streamGenerate(
  body: GenerateBody,
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    // The daemon rejects an invalid brief lock with HTTP 400 and a structured
    // body: { detail: { error, problems: [...] } }. Surface it specifically so
    // the UI can list the problems instead of showing a generic failure.
    if (res.status === 400) {
      try {
        const data = await res.json();
        const detail = data?.detail;
        if (detail && Array.isArray(detail.problems)) {
          throw new DiscoveryError(
            detail.error || "Invalid brief lock.",
            detail.problems,
          );
        }
      } catch (err) {
        if (err instanceof DiscoveryError) throw err;
        // fall through to the generic error below
      }
    }
    throw new Error(`${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // SSE frames are separated by a blank line ("\n\n").
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          onEvent(JSON.parse(payload) as StreamEvent);
        } catch {
          // ignore malformed frames
        }
      }
    }
  }
}
