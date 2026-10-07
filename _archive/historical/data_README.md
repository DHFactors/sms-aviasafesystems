<!--
ARCHIVED.
Original path: data\README.md
Archived: 2026-10-07
Category: historical
Reason: Data Archive notes; reference-data notes superseded by docs/status.md.
Authority: none. This file is a historical record only.
-->

@"
# Data Archive

Source-of-truth data files. Reference archive — not fetched
or executed at runtime.

| File | Purpose | Imported to |
|------|---------|-------------|
| Master Logsheet-YYYY.xlsx | Operator safety logsheets | Phase 2B Historical Import |
| hfacs_nanocodes.csv | HFACS nanocodes | Postgres table hfacs_nanocodes |
| icao_adrep_taxonomies.csv | ICAO ADREP categories | Postgres table icao_adrep_taxonomies |

Every source dataset lives here, even after import.
Do not modify in place — add a dated version if data changes.
"@ | Set-Content data\README.md