// Split a finding into what the drawings say and what production says, the same way the
// Excel report does (src/ludwig/report/__init__.py: by_side).
import type { Finding, SourceRef } from "./api";

export type Side = "architect" | "erp";

const UNMATCHED: Record<string, Side> = { "architect set": "architect", "production data": "erp" };

function sideOf(key: string): Side | null {
  if (key in UNMATCHED) return UNMATCHED[key];
  const [side, ...rest] = key.split(".");
  if ((side === "architect" || side === "erp") && rest.length > 0) return side;
  return null;
}

export interface Sides {
  values: Record<Side, unknown>;
  sources: Record<Side, SourceRef[]>;
}

export function bySide(f: Pick<Finding, "measured" | "evidence">): Sides {
  const sources = {
    architect: f.evidence.filter((s) => s.kind !== "erp"),
    erp: f.evidence.filter((s) => s.kind === "erp"),
  };
  const values: Record<Side, unknown> = { architect: undefined, erp: undefined };
  const m = f.measured;
  if (m && typeof m === "object" && !Array.isArray(m)) {
    const keys = Object.keys(m);
    if (keys.length > 0 && keys.every((k) => sideOf(k) !== null)) {
      for (const k of keys) values[sideOf(k)!] = (m as Record<string, unknown>)[k];
      return { values, sources };
    }
  }
  if (sources.erp.length > 0 && sources.architect.length === 0) values.erp = m;
  else values.architect = m;
  return { values, sources };
}

export function formatValue(value: unknown): string {
  if (value === undefined) return "";
  if (value === null) return "not set";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(+value.toFixed(3));
  if (Array.isArray(value)) return value.map(formatValue).join(" / ");
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.map(([k, v]) => `${k}: ${formatValue(v)}`).join(", ");
  }
  return String(value);
}

export function describeSource(s: SourceRef): string {
  const parts = [s.file];
  if (s.ifc_guid) parts.push(`GlobalId ${s.ifc_guid}`);
  if (s.sheet) parts.push(`sheet ${s.sheet}`);
  if (s.cell) parts.push(`cell ${s.cell}`);
  if (s.dxf_handle) parts.push(`handle ${s.dxf_handle}`);
  if (s.layer) parts.push(`layer ${s.layer}`);
  if (s.page !== undefined) parts.push(`page ${s.page}`);
  return parts.join(", ");
}
