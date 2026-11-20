import {
  blockers,
  hints,
  type Mapping,
  setColumn,
  setProp,
  setTypeColumn,
  setTypeValue,
  setValueTranslation,
  updateProp,
  usedHeaders,
} from "./mapping";

const base: Mapping = { header_row: 1, type: "frame", units: "mm", columns: { mark: "Merk" } };

test("choosing no column removes the field", () => {
  const m = setColumn(setColumn(base, "width_mm", "Breedte"), "mark", "");
  expect(m.columns).toEqual({ width_mm: "Breedte" });
  expect(base.columns).toEqual({ mark: "Merk" });
});

test("a property takes its kind from the list and goes away when cleared", () => {
  const m = setProp(base, "fire_rating_min", "Brandwerendheid");
  expect(m.props).toEqual({ fire_rating_min: { column: "Brandwerendheid", as: "number" } });
  expect("props" in setProp(m, "fire_rating_min", "")).toBe(false);
});

test("re-choosing the same column keeps value translations", () => {
  let m = setProp(base, "opening_direction", "Draairichting");
  m = setValueTranslation(m, "opening_direction", "L", "left");
  expect(setProp(m, "opening_direction", "Draairichting").props?.opening_direction.values).toEqual({ L: "left" });
  m = setValueTranslation(m, "opening_direction", "L", "");
  expect(m.props?.opening_direction).toEqual({ column: "Draairichting", as: "text" });
});

test("the fire rating default can be switched off", () => {
  let m = updateProp(setProp(base, "fire_rating_min", "FR"), "fire_rating_min", { default: 0 });
  expect(m.props?.fire_rating_min.default).toBe(0);
  m = updateProp(m, "fire_rating_min", { default: undefined });
  expect("default" in (m.props?.fire_rating_min ?? {})).toBe(false);
});

test("a type column needs at least one value marked as an element", () => {
  let m = setTypeColumn(base, "Artikelsoort");
  expect(blockers(m)).toEqual(["Say which values in the type column are elements."]);
  m = setTypeValue(m, "Kozijn", "frame");
  expect(blockers(m)).toEqual([]);
  expect(usedHeaders(m)).toEqual(new Set(["Merk", "Artikelsoort"]));
  expect(setTypeColumn(m, "").type).toBe("frame");
});

test("hints name what will not be checked", () => {
  expect(blockers({ ...base, columns: {} })).toEqual(["Choose at least one column."]);
  expect(hints({ ...base, columns: {} })).toHaveLength(2);
  expect(hints(setColumn(setColumn(base, "width_mm", "B"), "height_mm", "H"))).toEqual([]);
});
