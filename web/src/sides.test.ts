import { bySide, describeSource, formatValue } from "./sides";

const erp = { file: "export.csv", kind: "erp" as const, cell: "F2" };
const ifc = { file: "model.ifc", kind: "ifc" as const, ifc_guid: "g1" };

test("compare findings put each path on its side", () => {
  const s = bySide({
    measured: { "architect.width_mm": { "model.ifc": 1200 }, "erp.width_mm": { "export.csv": 1180 } },
    evidence: [ifc, erp],
  });
  expect(s.values.architect).toEqual({ "model.ifc": 1200 });
  expect(s.values.erp).toEqual({ "export.csv": 1180 });
  expect(s.sources.erp).toEqual([erp]);
});

test("unmatched findings use their count keys", () => {
  const s = bySide({ measured: { "production data": 1, "architect set": 0 }, evidence: [erp] });
  expect(s.values).toEqual({ architect: 0, erp: 1 });
});

test("other findings go to the side of their evidence", () => {
  expect(bySide({ measured: 1650, evidence: [erp] }).values.erp).toBe(1650);
  expect(bySide({ measured: { "model.ifc": 3 }, evidence: [ifc] }).values.architect).toEqual({
    "model.ifc": 3,
  });
});

test("values and sources read like the Excel report", () => {
  expect(formatValue(null)).toBe("not set");
  expect(formatValue(1172.5)).toBe("1172.5");
  expect(formatValue({ "a.csv": { left: 2, right: 2 } })).toBe("a.csv: left: 2, right: 2");
  expect(describeSource(ifc)).toBe("model.ifc, GlobalId g1");
});
