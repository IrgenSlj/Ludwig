// Hash routes keep the service free to own every path under /api.
import { useEffect, useState } from "react";

export type Route =
  | { page: "projects" }
  | { page: "project"; id: number }
  | { page: "run"; id: number }
  | { page: "finding"; id: number }
  | { page: "packs" }
  | { page: "pack"; name: string }
  | { page: "activity" }
  | { page: "users" }
  | { page: "account" };

export function parse(hash: string): Route {
  const [, kind, id] = hash.replace(/^#/, "").split("/");
  const n = Number(id);
  if (kind === "packs") return id ? { page: "pack", name: decodeURIComponent(id) } : { page: "packs" };
  if (kind === "projects" && n) return { page: "project", id: n };
  if (kind === "runs" && n) return { page: "run", id: n };
  if (kind === "findings" && n) return { page: "finding", id: n };
  if (kind === "activity") return { page: "activity" };
  if (kind === "users") return { page: "users" };
  if (kind === "account") return { page: "account" };
  return { page: "projects" };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export const href = {
  projects: () => "#/",
  project: (id: number) => `#/projects/${id}`,
  run: (id: number) => `#/runs/${id}`,
  finding: (id: number) => `#/findings/${id}`,
  packs: () => "#/packs",
  pack: (name: string) => `#/packs/${encodeURIComponent(name)}`,
  activity: () => "#/activity",
  users: () => "#/users",
  account: () => "#/account",
};
