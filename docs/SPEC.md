# Ludwig — specification

## 1. Purpose

Before production starts, find differences between what the architect's documents
require and what has been prepared for production, and find breaches of the factory's
own limits and of project requirements.

## 2. Users and inputs

User: the work preparer at a fabricator. Secondary: the estimator and the project lead.

Inputs, in the order they are supported:

| Input | Phase | Read by |
|---|---|---|
| IFC model (IFC2x3, IFC4) | 1 | IfcOpenShell |
| Excel or CSV schedule | 1 | openpyxl / csv, with a column mapping |
| Production software export (CSV/Excel) | 2 | generic adapter with a mapping |
| DXF | 3 | ezdxf |
| Vector PDF | 3 | pdfplumber |
| DWG | 3 | converted to DXF outside the process |
| Word schedules | later | not planned until a pilot needs it |

Scanned drawings are out of scope.

## 3. Element table

Every parser and adapter produces `Element` records. Rules see only this table.

| Field | Type | Notes |
|---|---|---|
| `id` | str | stable within a run |
| `side` | `architect` or `erp` | which party the data came from |
| `type` | enum | `frame`, `window_sash`, `door_leaf`, `glazing`, `panel`, `hardware_set` |
| `mark` | str or None | the position mark, normalised (trimmed, upper case, no spaces) |
| `quantity` | int | default 1 |
| `width_mm`, `height_mm`, `depth_mm` | float or None | millimetres |
| `location` | str or None | storey or zone |
| `parent_id` | str or None | e.g. a sash inside a frame |
| `props` | dict | named properties, see below |
| `sources` | list of `SourceRef` | at least one |

`SourceRef`: `file`, `kind` (`ifc`, `sheet`, `dxf`, `pdf`, `erp`), and a locator
(`ifc_guid`, or `sheet` plus `cell`, or `dxf_handle` plus `layer`, or `page` plus `bbox`).
Each field value may carry its own source when it came from a different place than the
element itself.

Standard property names (extend only when a rule needs one): `fire_rating_min`,
`burglary_class`, `u_value`, `sound_reduction_db`, `glazing_type`, `opening_direction`,
`material`, `finish`, `threshold_type`, `ventilation_grille`.

A value that could not be read is `None`. It is never zero or an empty string.

## 4. Parsing rules

- Convert units at the boundary. Reject nothing: unreadable items become parse warnings.
- Each parser has a mapping file for office conventions (property set names, column
  headers, layer names, attribute tags). No convention is hard-coded.
- The same physical element described in two architect documents (model and schedule)
  produces two elements on the `architect` side. Consistency rules compare them.

## 5. Matching architect and ERP elements

1. Match by `type` and normalised `mark`.
2. If marks are missing on either side, match by `type`, `location`, and dimensions
   within the pack's match tolerance.
3. One-to-one only. If several candidates remain, the result is `ambiguous`.
4. Unmatched elements on either side become findings (`missing-in-erp`,
   `not-in-architect-set`).

Matching never uses an LLM.

## 6. Rule packs

```
packs/<name>/
  pack.yaml          # name, version, description, files, match tolerance
  checks.yaml        # rules
  limits.yaml        # factory-specific numbers
  requirements.ids   # optional, phase 4
  fixtures/<rule-id>/pass.* and fail.*
```

Rule kinds:

```yaml
- id: sash-width-max
  kind: require
  applies_to: {side: erp, type: window_sash}
  require: width_mm <= limits.sash.max_width_mm
  severity: blocker
  message: "Sash {mark}: width {width_mm} mm exceeds machine limit {limits.sash.max_width_mm} mm"

- id: erp-width-matches
  kind: compare
  applies_to: {type: frame}
  left: architect.width_mm
  right: erp.width_mm
  tolerance: 1
  severity: blocker

- id: model-vs-schedule-count
  kind: consistent
  applies_to: {side: architect, type: frame}
  group_by: mark
  field: quantity
  severity: warning

- id: missing-in-erp
  kind: unmatched
  applies_to: {type: frame}
  missing_on: erp          # or: architect (gives not-in-architect-set)
  severity: blocker
```

`compare` and `unmatched` rules run over matched positions (section 5). An ambiguous
position gives `not_checked` on every such rule; without production data each gives one
`not_checked` finding.

Expression language (used in `require`, and in `when` filters):

- Literals: numbers, strings in double quotes, `true`, `false`.
- Names: element fields, `props.<name>`, `limits.<path>`, `parent.<field>`.
- Operators: `+ - * /`, `== != < <= > >=`, `and or not`, `in [a, b, c]`, parentheses.
- Functions: `abs(x)`, `min(a, b)`, `max(a, b)`, `is_set(x)`.
- Nothing else. No attribute access beyond the paths above, no calls, no assignment.
- Any `None` operand makes the result `not_checked`, except inside `is_set`.

The language has its own tokenizer and parser. It is never passed to Python `eval`.

Severity: `blocker` (do not produce), `warning` (review), `info`.

## 7. Findings

| Field | Notes |
|---|---|
| `rule_id`, `pack`, `pack_version` | |
| `status` | `fail`, `pass`, `not_checked`, `not_applicable` |
| `severity` | from the rule |
| `element_ids`, `mark` | one or two elements |
| `measured`, `expected` | values as evaluated |
| `message` | rendered from the pack template |
| `evidence` | list of `SourceRef` for every value used |
| `reason` | required when status is `not_checked` |

Reports list `fail` first, then `not_checked`. A report always states how many rules
ran, how many elements were covered, and how many checks could not be evaluated.

## 8. Outputs

- JSON: the canonical result, schema-versioned.
- Excel: one row per finding, for the work preparer.
- BCF (phase 4): for model checkers and coordination tools.
- PDF markup (phase 4): annotations on a copy of the source PDF.

## 9. LLM boundary

Allowed, inside `ludwig.assist` only, phase 5 onward:

- Draft a rule from specification text. The draft is shown to a person and saved only
  after they accept it; it must load and pass its fixtures like any other rule.
- Suggest a column or layer mapping for a new office convention, for a person to confirm.
- Rephrase a finding in plain language. The original finding stays attached.

Not allowed: deciding a status, changing a value, matching elements, dismissing findings.

Customer files are sent to a model only if the company has enabled it. The provider is
configurable and an EU-hosted option must exist.

## 10. Non-functional

- A run on 2,000 elements and 100 rules finishes in under 60 seconds on a laptop.
- Same inputs and pack version give byte-identical JSON.
- No network access is needed for a check.
- Files stay within the company's project; nothing is shared across companies.

## 11. Open questions

1. Which production software is first, and what its export contains (PLAN 2.1).
2. Whether marks are reliably present in ERP exports; this decides how much the
   fallback matching matters.
3. Which Dutch requirements belong in the first pack beyond factory limits. Each must
   be checked against the current official text before it becomes a rule.
4. The exact package for writing BCF, and whether IfcOpenShell's IDS parser can be
   reused for reading IDS files. Verify before adding either.
