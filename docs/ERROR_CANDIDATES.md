# Error candidates

Prompts for the error catalogue (PLAN 0.5), drawn from public sources and the element
model, so that writing the catalogue is a matter of confirming, striking and costing rows.

**These are not evidence.** The phase 0 gate counts only entries in
`docs/ERROR_CATALOGUE.md`, written from practice. A candidate moves there when Irgen has
seen it happen and can state what it cost; otherwise it is struck.

Columns:

- **Rule shape** — the rule kind (SPEC section 6) and the field that would catch it.
  `covered` means a rule in `packs/joinery-nl` already does.
- **Data** — `spec`: the field is in SPEC section 3; `new`: a field would have to be added.
- **Catchable** — proposal for PLAN 0.6: `files`, `erp` or `no`.

| # | Candidate | Rule shape | Data | Catchable |
|---|---|---|---|---|
| 1 | Production quantity per mark differs from the drawings | covered: `erp-quantity` | spec | erp |
| 2 | Width or height entered differently for production | covered: `erp-width`, `erp-height` | spec | erp |
| 3 | Opening direction (left/right, in/out) swapped | covered: `erp-opening-direction` | spec | erp |
| 4 | Glazing type in production differs from the drawings | covered: `erp-glazing-type` | spec | erp |
| 5 | Fire rating dropped between drawings and production | covered: `erp-fire-rating` | spec | erp |
| 6 | A position on the drawings never entered for production | covered: `missing-in-erp` | spec | erp |
| 7 | A position produced after it was removed in a revision | covered: `not-in-architect-set` | spec | erp |
| 8 | Burglary class lower in production than specified [3] | covered: `erp-burglary-class` | spec | erp |
| 9 | Thermal value (glass or frame U-value) differs from the specification | covered: `erp-u-value` | spec | erp |
| 10 | Sound reduction requirement not carried into production | covered: `erp-sound-reduction` | spec | erp |
| 11 | Threshold type wrong (e.g. standard sill where a level threshold was asked) | covered: `erp-threshold-type` | spec | erp |
| 12 | Ventilation grille missing in production | covered: `erp-ventilation-grille` | spec | erp |
| 13 | Colour or finish wrong, or inside and outside swapped | covered: `erp-finish`; inside/outside needs two fields | new | erp |
| 14 | Wood species or material differs from the specification | covered: `erp-material` | spec | erp |
| 15 | Model and schedule disagree on the count per mark | covered: `drawings-count` | spec | files |
| 16 | Model and schedule disagree on the size per mark | covered: `drawings-width`, `drawings-height` | spec | files |
| 17 | Drawing and schedule disagree on opening direction or glazing | covered: `drawings-opening-direction`, `drawings-glazing-type`, `drawings-fire-rating` | spec | files |
| 18 | Sash larger or heavier than the hardware or machine allows | require on `window_sash` against `limits.sash.*` | spec (weight: new) | erp |
| 19 | Glass pane over the factory's handling size or weight | require on `glazing` against `limits.glass.*` | spec (weight: new) | erp |
| 20 | Safety glass missing where NEN 3569 asks for it (doors, low glazing) [1] | require on `glazing` with `parent.type`; sill height for low glazing | new (sill height) | files |
| 21 | Reachable element in housing below burglary class 2 (NEN 5096) [3] | require `props.burglary_class` with `when` on location | spec | files |
| 22 | Glazing in a fire-rated door not fire-rated itself | require on `glazing` with `parent.props.fire_rating_min` | spec | files |
| 23 | Rough opening on site differs from the drawing | needs a site measurement | — | no |
| 24 | Connection detail (frame to wall, sill, cavity) drawn wrongly | drawing detail, not a table value | — | no |

Notes on the sources:

- [1] NEN 3569 covers vertical glazing supported on all sides with a clear size above
  150 mm. The building regulations do not cite it directly; it is agreed in contracts and
  a 2022 court ruling called it the standard of care for a front door. Check the current
  text before a rule cites it.
- [2] SBR puts failure costs in Dutch construction at 5–10 % of production value; time
  pressure and poor work preparation are the causes named most often.
- [3] Burglary class 2 per NEN 5096 for reachable facade elements of dwellings was a
  Bouwbesluit requirement; check the current article in the Besluit bouwwerken
  leefomgeving before a rule cites it.

Sources:

- [glas.nl, NEN 3569:2018 toelichting](https://www.glas.nl/storage/documents/nen3569-2018-toelichting-19f20302d0f51a2180a909dc4fc7dc9e.pdf)
- [omgevingsweb.nl, ruling ECLI:NL:GHSHE:2022:103](https://omgevingsweb.nl/jurisprudentie/eclinlghshe2022103/)
- [ABN AMRO, Verspilde moeite: faalkosten in de bouwsector](https://www.abnamro.nl/nl/media/Verspilde%20moeite.%20Over%20faalkosten%20in%20de%20bouwsector_tcm16-64849.pdf)
- [Staatsblad 1998, 573 (inbraakwerendheid)](https://zoek.officielebekendmakingen.nl/stb-1998-573.pdf)
- [Kiwa, PKVW beveiligingsrichtlijn 2021](https://careers.kiwa.com/globalassets/netherlands/kiwa-ncp/pdf/pkvw-beveiligingsrichtlijn-2021.pdf)
