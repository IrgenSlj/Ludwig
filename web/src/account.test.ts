import { describe as describeEvent } from "./pages/Account";

const event = (action: string, detail: Record<string, unknown>) => ({
  id: 1,
  created: "2026-11-21T10:00:00+00:00",
  user: "anna",
  action,
  project_id: 3,
  detail,
});

test("activity lines name files, runs, rules and limits", () => {
  expect(describeEvent(event("file uploaded", { upload: 4, filename: "export.csv", role: "erp" }))).toBe(
    "export.csv · (erp)",
  );
  expect(describeEvent(event("check run", { run: 7, pack: "joinery-nl 0.2.0" }))).toBe("run 7 · joinery-nl 0.2.0");
  expect(describeEvent(event("finding dismissed", { finding: 9, rule: "erp-width", mark: "K1" }))).toBe(
    "erp-width K1",
  );
  expect(describeEvent(event("limits changed", { pack: "joinery-nl", values: { "reconcile.width_tolerance_mm": 2 } }))).toBe(
    "joinery-nl · reconcile.width_tolerance_mm = 2",
  );
  expect(describeEvent(event("projects deleted", { projects: [1, 2], days: 90 }))).toBe("projects 1, 2 after 90 days");
});
