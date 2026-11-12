# Fixtures

Public sample inputs shared by tests. Every file is unmodified from its source; only the
file name was changed. Invented fixtures (seeded errors, per-rule pass/fail files) live
next to the rule that uses them under `packs/<name>/fixtures/`.

Invented fixtures in this folder (no source, licence: same as the repository):

| File | Contents |
|---|---|
| `schedule/duplex_joinery_schedule.csv` | Dutch-style joinery schedule (kozijnstaat) agreeing with the Duplex model: 12 rows, 38 units, `;` separated, decimal comma |
| `schedule/duplex_joinery_schedule_seeded.csv` | The same schedule with three seeded mismatches: mark 02 quantity 8 → 7, mark 05 width 4835 → 4800, mark 56 row removed |
| `schedule/*.mapping.yaml` | Column mappings for the invented schedule and for the COBie `Type` sheet |
| `erp/duplex_erp_export.csv` | Production export (order lines) for the Duplex project, agreeing with the model and the schedule: 12 frame lines plus one non-joinery line, `,` separated, decimal point. Column names are invented, not taken from any real ERP |
| `erp/duplex_erp_export_seeded.csv` | The same export with ten seeded mismatches (PLAN phase 2 gate): 01 glazing Triple, 02 quantity 6, 03 height 795, 05 width 4855, 28 both pairs right-hand, 32 left/right counts swapped, 33 fire rating left blank, 36 width 1127.5, 56 line removed, 99 extra line |
| `erp/*.mapping.yaml` | Column mappings for those exports |
| `dxf/duplex_joinery_plan.dxf` | The Duplex joinery as a 2D delivery: one attributed block reference per opening on layer `KOZIJNEN` (MERK, BREEDTE for windows, HOOGTE, VERDIEPING, DRAAIRICHTING; door widths only as block extents). Written by `tools/make_duplex_2d.py` from the Duplex model; same bytes on every run |
| `dxf/duplex_joinery_schedule.dxf` + `.mapping.yaml` | The invented joinery schedule drawn as a ruled table (LINEs and TEXT on layer `STAAT`); written by the same script from the CSV |

Counts below are raw entity counts from the file text, not hand counts of physical
elements. PLAN 1.2 adds the hand count.

| File | Source | Licence | Contents |
|---|---|---|---|
| `ifc/duplex_architectural_ifc2x3.ifc` | buildingSMART Sample-Test-Files, `IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment/Duplex_A_20110907.ifc` | CC BY 4.0 | IFC2X3; 24 `IfcWindow`, 14 `IfcDoor`, 6 window styles, 6 door styles |
| `ifc/clinic_architectural_ifc2x3.ifc` | buildingSMART Sample-Test-Files, `IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic/Clinic_Architectural.ifc` | CC BY 4.0 | IFC2X3; 58 `IfcWindow`, 254 `IfcDoor`, 1 window style, 19 door styles |
| `schedule/duplex_design_cobie.xlsx` | buildingSMART Sample-Test-Files, `IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment/2012-03-23-Duplex-Design.xlsx` | CC BY 4.0 | COBie 2.4 workbook for the Duplex model; `Type` sheet has Door Types A–D and Window Types A–D, `Component` sheet the instances |
| `dxf/ezdxf_wipeout_door.dxf` | ezdxf, `examples_dxf/wipeout_door.dxf` | MIT | AC1032 (R2018); one door block `wipeout_door`, two inserts, no attributes |

Repository: https://github.com/buildingsmart-community/Sample-Test-Files and
https://github.com/mozman/ezdxf. Retrieved 2026-11-11.

Required attribution for the buildingSMART files:
BSI (2020) "Duplex Apartment Test Files," buildingSMART International, and
BSI (2020) "Medical-Dental Test Files," buildingSMART International,
https://github.com/buildingsmart-community/Sample-Test-Files.

## Known gaps

- No IFC4 sample with windows and doors under a usable licence was found. IFC4 coverage
  comes from an invented model in phase 1.
- The public DXF block has no attributes; attributed joinery blocks come from the invented
  `duplex_joinery_plan.dxf`.
- The public schedule is a COBie export, not a joinery schedule as an architect draws it
  up; the invented `duplex_joinery_schedule.csv` covers that. COBie writes 0 for unknown
  nominal sizes, which its mapping reads as not set.
- Rejected: the Schependomlaan dataset (Dutch, has windows and doors) is licensed for
  scientific and academic use only.

## Checksums (SHA-256)

```
26794284e4e52db626b889fbbaf847fabb3c6ac85603096af244d7b6d95448bb  dxf/ezdxf_wipeout_door.dxf
2ac970ce065ecac4e0c9e5f453a257169e90d0067f419b7e33533a64ef837880  ifc/clinic_architectural_ifc2x3.ifc
b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed  ifc/duplex_architectural_ifc2x3.ifc
ff7dde2cf3c71da2f7854ca8e21b5b73c513b2acc219d5eaf19aeaba8423bf9e  schedule/duplex_design_cobie.xlsx
```
