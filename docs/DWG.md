# DWG input

Ludwig does not read DWG. No DWG library runs inside Ludwig: the open one (LibreDWG) is
GPL and the closed ones need a licence for in-process use. A DWG drawing is converted to
DXF first, by a separate program, and the DXF is checked.

## Conversion step

1. Convert each DWG to DXF (AutoCAD 2018 DXF or newer, ASCII):
   - **ODA File Converter** (Open Design Alliance, free download, proprietary licence).
     Command line, one folder at a time:
     ```
     ODAFileConverter <in-folder> <out-folder> ACAD2018 DXF 0 1 "*.DWG"
     ```
     The arguments are input folder, output folder, output version, output type,
     recurse (0/1), audit (0/1) and an input filter.
   - Or **AutoCAD / BricsCAD / DraftSight**: `SAVEAS` → DXF, or `DXFOUT`.
2. Keep the DXF next to the DWG with the same name, and add `<name>.mapping.yaml` if the
   office uses its own layer names, block names or attribute tags (see
   `src/ludwig/parsers/mappings/dxf_default.yaml`).
3. Run `ludwig check --architect drawing.dxf ...`.

Ludwig reports where values came from by DXF entity handle. Converters keep handles,
so a handle can be found in the original DWG.

## Rules for this step

- The converter runs as its own process, started by a person or a script outside
  Ludwig. Ludwig never links or imports it.
- Before a converter is shipped with Ludwig or run on a server for customers, check its
  licence terms for that use. The ODA File Converter's terms of use apply to whoever
  downloads it; they are not checked here.
- Passing a `.dwg` to `ludwig check` is a usage error (exit 2) that points here.
