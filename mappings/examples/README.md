# Example office mappings

Each office names layers, blocks, attribute tags, property sets and schedule columns its
own way. Ludwig keeps those conventions in mapping files, never in code (SPEC section 4).

Put the mapping next to the file it describes, named `<file name>.mapping.yaml`:

| Input | Mapping beside it | Without one |
|---|---|---|
| `model.ifc` | optional, IFC mapping | `src/ludwig/parsers/mappings/ifc_default.yaml` |
| `plan.dxf` | optional, DXF mapping | `src/ludwig/parsers/mappings/dxf_default.yaml` |
| `staat.xlsx` / `.csv` / `.pdf` | required, schedule mapping | usage error |
| `export.csv` (`--erp`) | required, or `--mapping FILE` | usage error |

Files here are starting points to copy, not used by any test fixture as-is:

- `dxf_aia_layers.yaml` — drawings on AIA/US National CAD Standard layers (`A-DOOR`,
  `A-GLAZ`) with English attribute tags.
- `dxf_office_tags.yaml` — an office that numbers frames with its own tags (`KOZ_NR`,
  `B_MM`, `H_MM`) on one layer, with sizes in centimetres.
- `ifc_reference_mark.yaml` — models that keep the mark in `Pset_*Common.Reference`
  instead of Revit's Type Mark.
