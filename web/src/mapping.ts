// Column mapping as edited in the web app; the service checks and stores it (PLAN 5.7).

export const ELEMENT_TYPES = ["frame", "window_sash", "door_leaf", "glazing", "panel", "hardware_set"] as const;
export type ElementType = (typeof ELEMENT_TYPES)[number];

export const TYPE_LABELS: Record<ElementType, string> = {
  frame: "Frame",
  window_sash: "Window sash",
  door_leaf: "Door leaf",
  glazing: "Glazing",
  panel: "Panel",
  hardware_set: "Hardware set",
};

export const FIELDS: { key: string; label: string }[] = [
  { key: "mark", label: "Mark (position)" },
  { key: "quantity", label: "Quantity" },
  { key: "width_mm", label: "Width" },
  { key: "height_mm", label: "Height" },
  { key: "depth_mm", label: "Depth" },
  { key: "location", label: "Storey or zone" },
];

export const PROPS: { key: string; label: string; as: "number" | "text" }[] = [
  { key: "opening_direction", label: "Opening direction", as: "text" },
  { key: "fire_rating_min", label: "Fire rating (minutes)", as: "number" },
  { key: "glazing_type", label: "Glazing type", as: "text" },
  { key: "burglary_class", label: "Burglary class", as: "number" },
  { key: "u_value", label: "U-value", as: "number" },
  { key: "sound_reduction_db", label: "Sound reduction (dB)", as: "number" },
  { key: "threshold_type", label: "Threshold type", as: "text" },
  { key: "ventilation_grille", label: "Ventilation grille", as: "text" },
  { key: "material", label: "Material or wood species", as: "text" },
  { key: "finish", label: "Colour or finish", as: "text" },
];

export interface PropSpec {
  column: string;
  as: "number" | "text";
  values?: Record<string, string>;
  default?: number;
}

export interface TypeByColumn {
  column: string;
  values: Record<string, ElementType>;
  other: "skip" | "warn";
}

export interface Mapping {
  sheet?: string;
  header_row: number;
  type: ElementType | TypeByColumn;
  units: "mm" | "cm" | "m";
  columns: Record<string, string>;
  props?: Record<string, PropSpec>;
}

export interface Proposal {
  header_row: number;
  headers: string[];
  sample: string[][];
  values: Record<string, string[]>;
  mapping: Mapping;
  sheets: string[];
  previous: { upload: number; filename: string; project: number; mapping: Mapping }[];
}

export interface Preview {
  elements: number;
  quantity: number;
  warnings: string[];
  more_warnings: number;
  upload: { id: number; filename: string } | null;
}

export function setColumn(m: Mapping, field: string, header: string): Mapping {
  const columns = { ...m.columns };
  if (header) columns[field] = header;
  else delete columns[field];
  return { ...m, columns };
}

export function setProp(m: Mapping, key: string, header: string): Mapping {
  const props = { ...(m.props ?? {}) };
  const kind = PROPS.find((p) => p.key === key)?.as ?? "text";
  if (!header) delete props[key];
  else if (props[key]?.column !== header) props[key] = { column: header, as: kind };
  const { props: _old, ...rest } = m;
  return Object.keys(props).length ? { ...rest, props } : rest;
}

export function updateProp(m: Mapping, key: string, change: Partial<PropSpec>): Mapping {
  const spec = m.props?.[key];
  if (!spec) return m;
  const merged: PropSpec = { ...spec, ...change };
  for (const k of Object.keys(change) as (keyof PropSpec)[]) if (change[k] === undefined) delete merged[k];
  return { ...m, props: { ...m.props, [key]: merged } };
}

// Values the user left empty are kept as they are in the file.
export function setValueTranslation(m: Mapping, key: string, raw: string, to: string): Mapping {
  const values = { ...(m.props?.[key]?.values ?? {}) };
  if (to) values[raw] = to;
  else delete values[raw];
  return updateProp(m, key, { values: Object.keys(values).length ? values : undefined });
}

export function setTypeColumn(m: Mapping, column: string): Mapping {
  if (!column) return { ...m, type: "frame" };
  return { ...m, type: { column, values: {}, other: "skip" } };
}

export function setTypeValue(m: Mapping, raw: string, to: ElementType | ""): Mapping {
  if (typeof m.type === "string") return m;
  const values = { ...m.type.values };
  if (to) values[raw] = to;
  else delete values[raw];
  return { ...m, type: { ...m.type, values } };
}

export function usedHeaders(m: Mapping): Set<string> {
  const used = new Set(Object.values(m.columns));
  if (typeof m.type !== "string") used.add(m.type.column);
  for (const spec of Object.values(m.props ?? {})) used.add(spec.column);
  return used;
}

// Problems that stop saving; the service checks the rest.
export function blockers(m: Mapping): string[] {
  const out: string[] = [];
  if (!Object.keys(m.columns).length) out.push("Choose at least one column.");
  if (typeof m.type !== "string" && !Object.keys(m.type.values).length)
    out.push("Say which values in the type column are elements.");
  return out;
}

export function hints(m: Mapping): string[] {
  const out: string[] = [];
  if (!m.columns.mark) out.push("Without a mark column, positions are matched by size and storey only.");
  if (!m.columns.width_mm || !m.columns.height_mm) out.push("Without width and height, size rules are not checked.");
  return out;
}
