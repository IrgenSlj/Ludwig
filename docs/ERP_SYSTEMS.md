# Production software

Systems that Dutch joinery and window factories use for work preparation and production,
for PLAN 2.1 (name the production software, obtain an export or its column list).
Researched 2026-11-20 from public pages; none of them publishes its export columns.

| System | Supplier | Note |
|---|---|---|
| ECI Trimergo | ECI Software Solutions | ERP in use at Dutch frame factories |
| 3E-LOOK | 3E Datentechnik | ERP for window companies; has a Dutch office |
| OSD-ERP | OS Datensysteme | ERP and CAD/CAM for woodworking |
| Proginov | Proginov | ERP with a configurator for made-to-measure joinery |
| Exact for Production | Exact | general manufacturing ERP, not joinery-specific |

What this means for Ludwig: with no public export format, a vendor-specific adapter
cannot be written in advance. `adapters/erp_table.py` with a mapping file stays the way
in; the first real export, or a column list from a factory, gives the mapping.

What to ask a factory for: the system name and version, and one export of a finished
order (any format the system can produce) with names and addresses replaced.

Sources:

- [Centrum Hout, digital frame factories](https://www.centrumhout.nl/media/b307d34a-a5b3-4b60-af05-ec473eb94c7e.pdf)
- [3E, 3E-LOOK for the Netherlands](https://www.3e-it.com/uploads/attachment/download/127/3E_Faltblatt_Holland_2021_1mm.pdf)
- [Blum, OSD-ERP](https://www.blum.com/ph/en/services/industrial-production/cad-cam-interface/software-partners/osd/)
- [Proginov, industrial joinery](https://www.proginov.com/en/docs/industrial-joinery.pdf)
- [Exact for Production](https://files.exact.com/static/web/downloads/NL-MNF-Brochure-Exact-voor-Productie.pdf)
