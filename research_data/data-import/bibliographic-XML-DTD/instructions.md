# IPCC AR6 Bibliographic References

## Overview

This project imports IPCC AR6 bibliographic references into ClimateKG Wikibase.
Each reference becomes a Wikibase item linked to the chapter(s) in which it is cited.

The pipeline follows the standard ClimateKG import pattern:

```
source CSV  →  normalise_refs.py  →  references_normalised.csv
                                           │
                                    csv_to_xml.py
                                           │
                                    outputs/references.xml  (validated against bibliographic.dtd)
                                           │
                                    upload_to_wikibase.py
                                           │
                                    Wikibase items
```

---

## Files

| File | Description |
|------|-------------|
| `references-source.csv` | *(to be added)* Original source CSV of bibliographic references |
| `references_normalised.csv` | Output of `normalise_refs.py` — cleaned, deduplicated references |
| `bibliographic.dtd` | DTD defining the XML structure |
| `normalise_refs.py` | Applies normalisation rules to source CSV |
| `csv_to_xml.py` | Generates `outputs/references.xml` from `references_normalised.csv` |
| `outputs/references.xml` | Generated XML (one `<reference>` per item) |
| `upload_to_wikibase.py` | Imports `outputs/references.xml` into Wikibase |

---

## Source Data

> **TODO**: Describe the source CSV format here once the source file is obtained.

Expected columns (TBC based on source):

| Column | Description |
|--------|-------------|
| `Citation_Key` | Short citation key (e.g. `Smith2021`) |
| `Authors` | Semicolon-separated author list |
| `Year` | Publication year (4 digits) |
| `Title` | Full title of the work |
| `Publication_Type` | `article`, `book`, `report`, `chapter`, etc. |
| `Source` | Journal name / book title / publisher |
| `Volume` | Volume number (articles) |
| `Issue` | Issue number (articles) |
| `Pages` | Page range (e.g. `123-145`) |
| `DOI` | DOI string (without `https://doi.org/` prefix) |
| `URL` | Full URL |
| `Report` | IPCC report code (`WGI`, `WGII`, `WGIII`, `SYR`, `SR1.5`, `SRCCL`, `SROCC`) |
| `Chapter` | Chapter label |
| `Chapter_QID` | Wikibase QID for the chapter item |

---

## Data normalisation — `references-source.csv` → `references_normalised.csv`

Script: `normalise_refs.py`

### Normalisation steps (TBC)

> **TODO**: Document normalisation steps once source data is analysed.

Anticipated steps:
1. Whitespace stripping on all string fields
2. Year — validate 4-digit integer
3. DOI — strip protocol prefix if present (normalise to bare DOI)
4. Publication_Type — expand/standardise values
5. ClimateKG_Ref_ID — assign stable `REF0001`…`REFnnnn` per unique reference
6. Column rename and reorder

---

## XML structure summary

Each unique reference becomes one `<reference id="REF0001">` element containing:
- Bibliographic elements: `<citation_key>`, `<authors>`, `<year>`, `<title>`,
  `<publication_type>`, `<source>`, `<volume>`, `<issue>`, `<pages>`, `<doi>`, `<url>`
- `<citations>` — one `<citation chapter_qid="Q190" report="WGI" chapter="...">` per
  chapter that cites this reference, containing `<source_url>` and `<date_accessed>`

---

## Wikibase data model

Each `<reference>` creates one Wikibase item:

| Wikibase field | Source | Type |
|---|---|---|
| Label (en) | `Citation_Key` | label |
| Description (en) | `"IPCC AR6 bibliographic reference"` | description |
| P1 instance of | `REFERENCE_CLASS_QID` | WikibaseItem |
| `P_REF_ID` ClimateKG Reference ID | `climatkg_ref_id` | String |
| `P_CITATION_KEY` citation key | `citation_key` | String |
| `P_AUTHORS` authors | `authors` | String |
| `P_YEAR` year | `year` | Time (year precision) |
| `P_TITLE` title | `title` | String |
| `P_PUBLICATION_TYPE` publication type | `publication_type` | String |
| `P_SOURCE` source (journal/book) | `source` | String |
| `P_VOLUME` volume | `volume` | String |
| `P_ISSUE` issue | `issue` | String |
| `P_PAGES` pages | `pages` | String |
| `P_DOI` DOI | `doi` | ExternalID |
| `P_URL` URL | `url` | url |
| `P_CITED_IN_CHAPTER` cited in chapter | `chapter_qid` | WikibaseItem |
| ↳ reference P17 reference URL | `source_url` | url |
| ↳ reference P18 date accessed | `date_accessed` | time |

> **Note**: Properties P20–P28 are used by the **Authors** import (P20=ClimateKG Author ID
> through P28=role). Properties P29–P33 are used by the **DOI Enrichment** pipeline
> (see below). New properties for bibliographic references will be assigned P34+ during bootstrap.

---

## IPCC AR6 report QID map

| Report code | QID | Label |
|---|---|---|
| SR1.5 | Q10 | Special Report on Global Warming of 1.5 degrees C |
| SRCCL | Q35 | Special Report on Climate Change and Land |
| SROCC | Q57 | Special Report on the Ocean and Cryosphere in a Changing Climate |
| SYR | Q189 | Synthesis Report |
| WGI | Q77 | Working Group I: The Physical Science Basis |
| WGII | Q106 | Working Group II: Impacts, Adaptation and Vulnerability |
| WGIII | Q150 | Working Group III: Mitigation of Climate Change |

---

## Import workflow (two-run bootstrap)

### Prerequisites

```bash
pip install wikibaseintegrator python-dotenv
```

Ensure `WB_PASSWORD` is set in `C:\Wikibase\.env`.

### Step 0 — Experimental workflow snapshot (recommended)

```powershell
.\scripts\experimental-import-workflow.ps1 start
```

### Step 1 — Normalise source CSV

```bash
python normalise_refs.py
```

### Step 2 — Generate XML

```bash
python csv_to_xml.py
```

### Step 3 — Bootstrap (first run — creates class item and properties)

```bash
python upload_to_wikibase.py
```

Copy the printed `REFERENCE_CLASS_QID`, `P_REF_ID`, etc. values into `C:\Wikibase\.env`,
then re-run.

> **Note**: Properties P17 (reference URL) and P18 (date accessed) are pre-existing —
> do not recreate them. The bootstrap creates only the new Reference class item and
> bibliographic properties (P29+).

### Step 4 — Full import

```bash
python upload_to_wikibase.py
# or dry-run first:
DRY_RUN=true python upload_to_wikibase.py
# or limited batch:
LIMIT=10 python upload_to_wikibase.py
```

Results are logged to `outputs/upload_log.json`.

### Step 5 — Approve or rollback

```powershell
.\scripts\experimental-import-workflow.ps1 approve
# or:
.\scripts\experimental-import-workflow.ps1 rollback
```

### Bootstrap QIDs

> **TODO**: Fill in after first bootstrap run.

| Variable | ID | Label |
|---|---|---|
| `REFERENCE_CLASS_QID` | *(TBD)* | Reference |
| `P_REF_ID` | *(TBD)* | ClimateKG Reference ID |
| `P_CITATION_KEY` | *(TBD)* | citation key |
| `P_AUTHORS` | *(TBD)* | authors |
| `P_YEAR` | *(TBD)* | year |
| `P_TITLE` | *(TBD)* | title |
| `P_PUBLICATION_TYPE` | *(TBD)* | publication type |
| `P_SOURCE` | *(TBD)* | source |
| `P_VOLUME` | *(TBD)* | volume |
| `P_ISSUE` | *(TBD)* | issue |
| `P_PAGES` | *(TBD)* | pages |
| `P_DOI` | *(TBD)* | DOI |
| `P_URL` | *(TBD)* | URL |
| `P_CITED_IN_CHAPTER` | *(TBD)* | cited in chapter |

### Completed import record

| Date | Environment | References created | QID range | Errors |
|---|---|---|---|---|
| *(pending)* | | | | |

---

## DOI Enrichment Pipeline

Adds Crossref DOI-sourced bibliographic property statements to existing Series (Q4)
and Chapter (Q6) items. Runs as a post-import enrichment step — items must already
exist before this pipeline is used.

> **Re-run required after any DB pull/restore.** The bootstrap (P20–P24) and
> import were run on LOCAL only (2026-06-01). After pulling DEV → LOCAL the
> database is replaced; properties and statements will be gone. Run bootstrap
> then import again. The new PIDs may differ if DEV already has P20+ occupied —
> check `outputs/property_map.json` after bootstrap. Also ensure
> `$wgWBRepoSettings['string-limits']['VT:string']['length'] = 2500` is in
> `LocalSettings.general.php` on the target environment before importing.

### Pipeline

```
series_chapters.csv  →  csv_to_enrichment_xml.py  →  outputs/enrichment.xml
                                                              │
                                                    import_doi_enrichment.py
                                                              │
                                                    Wikibase items (P20–P24 added)
```

### Files

| File | Description |
|------|-------------|
| `series_chapters.csv` | 95 rows (7 Series Q4 + 88 Chapters Q6) with Crossref DOI metadata |
| `bibliographic-enrichment.dtd` | DTD for the enrichment XML format |
| `enrich_csv_doi.py` | Fetches Crossref metadata and adds columns to CSV |
| `csv_to_enrichment_xml.py` | Generates `outputs/enrichment.xml` from CSV |
| `outputs/enrichment.xml` | Generated XML — 95 items, 228 statements |
| `outputs/property_map.json` | Maps property labels to PIDs (written by bootstrap) |
| `import_doi_enrichment.py` | Two-mode script: bootstrap + import |
| `outputs/import_log.json` | Per-item import results |

### Bootstrapped properties (LOCAL, June 2026)

| PID | Label | Datatype | Scope |
|-----|-------|----------|-------|
| P29 | Publisher (DOI) | string | Series + Chapter |
| P30 | ISBN Electronic (DOI) | string | Series + Chapter |
| P31 | ISBN Print (DOI) | string | Series + Chapter |
| P32 | Licence URL (DOI) | url | Series only |
| P33 | Abstract (DOI) | string | Series only |

> **Note**: P20–P28 are now used by the Authors import. P29–P33 are the current DOI enrichment PIDs.

Reference provenance snaks use pre-existing properties:
- P17 reference URL, P18 date accessed, P19 source version (Crossref)

### Implementation notes

- Uses direct `wbcreateclaim` + `wbsetreference` API calls (not `wbi item.write()`),
  so existing sitelinks are never touched and the climatekg-wiki sitelink
  validation error is avoided.
- `wbcreateclaim` value must be `json.dumps("string value")` — not a datavalue object.
- `VT:string` length limit raised to 2500 in `LocalSettings.general.php` to
  accommodate DOI abstracts (497–1068 chars for these Series items).
- Duplicate detection: skips statements already present on the item.

### Usage

```powershell
# Bootstrap: create properties (already done — do not re-run)
python import_doi_enrichment.py --bootstrap

# Dry-run
$env:DRY_RUN="true"; python import_doi_enrichment.py

# Full import
python import_doi_enrichment.py

# Retry subset (e.g. first 7 Series items)
$env:OFFSET="0"; $env:LIMIT="7"; python import_doi_enrichment.py
```

### Completed import record

| Date | Environment | Items processed | Statements added | Errors | Notes |
|------|-------------|-----------------|------------------|--------|-------|
| 2026-06-01 | LOCAL | 95 (7 Series + 88 Chapters) | 228 | 0 | P20–P24 (rolled back) |
| 2026-06-02 | LOCAL | 95 (7 Series + 88 Chapters) | 228 | 0 | P29–P33 (after Authors import occupied P20–P28) |
