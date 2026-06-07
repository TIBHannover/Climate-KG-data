# IPCC AR6 Authors data

## Files

| File | Description |
|------|-------------|
| `authors-source.csv` | Original source CSV of IPCC AR6 authors |
| `authors.csv` | Working copy used as input to QID lookup |
| `authors_with_qids.csv` | Output of `lookup_chapter_qids.py` — adds `Chapter_QID_URL`, `Chapter_Label`, and `Match_Type` columns |
| `authors_normalised.csv` | Output of `normalise_authors.py` — normalised version of `authors_with_qids.csv` |
| `lookup_chapter_qids.py` | Looks up Wikibase QIDs for each (Report, Chapter) pair via SPARQL |
| `normalise_authors.py` | Applies data normalisation rules (see below) |

---

## Data normalisation — `authors_with_qids.csv` → `authors_normalised.csv`

Script: `normalise_authors.py`  
Run date: 2026-06-01  
Input rows: 1164  
Rows changed: 255

### Steps applied

#### 1. Whitespace stripping
All string fields are stripped of leading and trailing whitespace.  
*Result: 0 fields changed (no whitespace found in current data).*

#### 2. Country of Residence — short-form normalisation
The `Country of Residence` column used full official country names in some
cases where the `Citizenship` column used short-form equivalents. The
following mappings were applied to make the two columns consistent:

| Original value | Normalised value | Rows affected |
|----------------|-----------------|---------------|
| `United Kingdom (of Great Britain and Northern Ireland)` | `UK` | 96 |
| `United States of America` | `USA` | 132 |
| `Russian Federation` | `Russia` | 20 |
| `United Republic of Tanzania` | `Tanzania` | 7 |

#### 3. Last Name — title case
`Last Name` values were converted from ALL-CAPS to title case using Python's
`str.title()`, which correctly handles hyphens and accented characters.

Examples: `ALDUNCE` → `Aldunce`, `VAN VUUREN` → `Van Vuuren`,
`DIONGUE-NIANG` → `Diongue-Niang`, `ARAGóN-DURAND` → `Aragón-Durand`.  
*Result: 1164 rows changed.*

#### 4. Role — expand abbreviations and remove underscores

| Original | Normalised | Rows affected |
|----------|-----------|---------------|
| `CLA` | `Coordinating Lead Author` | 155 |
| `LA` | `Lead Author` | 723 |
| `RE` | `Review Editor` | 174 |
| `Core_Writing_Team` | `Core Writing Team` | 60 |
| `Lead` | *(unchanged)* | 15 |
| `Author` | *(unchanged)* | 37 |

`Lead` and `Author` appear only in WGII Cross-Chapter Papers and are retained as-is as legitimate distinct role labels in that context.

#### 5. CountIfs — column removed
The `CountIfs` column (an internal lookup count from the QID matching process) was dropped as it is not needed downstream.

#### 6. Chapter_Label — column removed
The `Chapter_Label` column was dropped as it is redundant with `Chapter_QID_URL`.

#### 7. Match_Type — column removed
The `Match_Type` column (QID match quality metadata: EXACT/FUZZY) was dropped as it is not needed for the Wikibase import.

#### 8. ClimateKG_Author_ID — new column added
A stable `ClimateKG_Author_ID` (format `AU0001`…`AU0932`) was assigned to each unique author, sorted alphabetically by Last Name then First Name. The same ID appears on all rows belonging to the same author, enabling the XML DTD generator to group chapter contributions per author entity.  
*Result: 932 unique authors across 1164 rows.*

#### 9. Chapter_QID — extracted from URL, URL column removed
The `Chapter_QID_URL` column contained environment-specific localhost URLs (e.g. `http://localhost:8080/entity/Q190`). The QID portion (`Q190`) was extracted into a new `Chapter_QID` column and the original URL column was dropped.

#### 10. Column rename and reorder
All column names were converted to underscore form (no spaces) for XML compatibility, and reordered into a logical author-first, chapter-contribution-second sequence:

| Final column | Source column |
|---|---|
| `ClimateKG_Author_ID` | *(new)* |
| `Last_Name` | `Last Name` |
| `First_Name` | `First Name` |
| `Gender` | `Gender` |
| `Citizenship` | `Citizenship` |
| `Country_of_Residence` | `Country of Residence` |
| `Affiliation` | `Affiliation` |
| `Report` | `Report` |
| `Chapter` | `Chapter` |
| `Chapter_QID` | *(extracted from `Chapter_QID_URL`)* |
| `Role` | `Role` |
| `Source_URL` | *(constant: `https://apps.ipcc.ch/report/authors/`)* |
| `Date_Accessed` | *(constant: `18 March 2026`)* |

## XML DTD import — `authors_normalised.csv` → Wikibase

### Files

| File | Role |
|------|------|
| `authors.dtd` | DTD defining the XML structure |
| `csv_to_xml.py` | Generates `outputs/authors.xml` from `authors_normalised.csv` |
| `outputs/authors.xml` | Generated XML (932 authors, 1164 chapter contributions) |
| `upload_to_wikibase.py` | Imports `outputs/authors.xml` into Wikibase |

### XML structure summary

Each unique author becomes one `<author id="AU0001">` element containing:
- Biographical elements: `<climatkg_author_id>`, `<last_name>`, `<first_name>`, `<gender>`, `<citizenship>`, `<country_of_residence>`, `<affiliation>`
- `<chapter_contributions>` — one `<contribution chapter_qid="Q190" report="SYR" chapter="...">` per chapter, containing `<role>`, `<source_url>`, `<date_accessed>`

### Wikibase data model

Each `<author>` creates one Wikibase item:

| Wikibase field | Source | Type |
|---|---|---|
| Label (en) | `First_Name Last_Name` | label |
| Description (en) | `"IPCC AR6 author"` | description |
| P1 instance of | `AUTHOR_CLASS_QID` | WikibaseItem |
| `P_AUTHOR_ID` ClimateKG Author ID | `climatkg_author_id` | String |
| `P_LAST_NAME` last name | `last_name` | String |
| `P_FIRST_NAME` first name | `first_name` | String |
| `P_GENDER` gender | `gender` | String |
| `P_CITIZENSHIP` citizenship | `citizenship` | String |
| `P_COUNTRY_RESIDENCE` country of residence | `country_of_residence` | String |
| `P_AFFILIATION` affiliation | `affiliation` | String |
| `P_CONTRIB_CHAPTER` contributed to chapter | `chapter_qid` (WikibaseItem) | WikibaseItem |
| ↳ qualifier `P_ROLE` role | `role` | String (qualifier) |
| ↳ reference P17 reference URL | `source_url` (`https://apps.ipcc.ch/report/authors/`) | url |
| ↳ reference P18 date accessed | `date_accessed` (18 March 2026) | time |

### Import workflow (two-run bootstrap)

#### Prerequisites

```bash
pip install wikibaseintegrator python-dotenv
```

Ensure `WB_PASSWORD` is set in `C:\Wikibase\.env`.

#### Step 0 — Experimental workflow snapshot (recommended)

Before any import, create a database snapshot so you can roll back:

```powershell
.\scripts\experimental-import-workflow.ps1 start
```

#### Step 1 — Regenerate XML (if CSV has changed)

```bash
python csv_to_xml.py
```

#### Step 2 — Bootstrap (first run — creates class item and properties)

```bash
python upload_to_wikibase.py
```

Copy the printed `AUTHOR_CLASS_QID`, `P_AUTHOR_ID`, `P_LAST_NAME`, etc. values
into `C:\Wikibase\.env`.

**Note:** Properties P17 (reference URL, `url` type) and P18 (date accessed,
`time` type) are pre-existing properties — do not recreate them. The bootstrap
only creates P20–P28 and the Author class item.

**Known bootstrap QIDs (LOCAL, 2026-06-01 experimental run):**

| Variable | ID | Label |
|---|---|---|
| `AUTHOR_CLASS_QID` | `Q3998` | Author |
| `P_AUTHOR_ID` | `P20` | ClimateKG Author ID |
| `P_LAST_NAME` | `P21` | last name |
| `P_FIRST_NAME` | `P22` | first name |
| `P_GENDER` | `P23` | gender |
| `P_CITIZENSHIP` | `P24` | citizenship |
| `P_COUNTRY_RESIDENCE` | `P25` | country of residence |
| `P_AFFILIATION` | `P26` | affiliation |
| `P_CONTRIB_CHAPTER` | `P27` | contributed to chapter |
| `P_ROLE` | `P28` | role |
| `P17_REFERENCE_URL` | `P17` | reference URL (pre-existing) |
| `P18_DATE_ACCESSED` | `P18` | date accessed (pre-existing) |

After a fresh DB sync from DEV, bootstrap will assign new IDs — update `.env` accordingly.

#### Step 3 — Import authors

```bash
python upload_to_wikibase.py
# or dry-run first:
DRY_RUN=true python upload_to_wikibase.py
# or limited batch:
LIMIT=10 python upload_to_wikibase.py
```

Results are logged to `outputs/upload_log.json`.

#### Step 4 — Approve or rollback (experimental workflow)

```powershell
# Keep the import:
.\scripts\experimental-import-workflow.ps1 approve

# Discard the import:
.\scripts\experimental-import-workflow.ps1 rollback
```

#### Completed import record

| Date | Environment | Authors created | QID range | Errors | Notes |
|---|---|---|---|---|---|
| 2026-06-02 | LOCAL | 932 | Q3999–Q4930 (Author class: Q3998) | 0 | Bug fixed: `MW_API_URL` default was `/api.php` — corrected to `/w/api.php` |



The following issue was identified during profiling but deliberately
excluded from normalisation:

| Issue | Decision | Rationale |
|-------|-----------|-----------|
| Role values `Author` and `Lead` (WGII Cross-Chapter Papers only) | **Left as-is** | These are legitimate distinct roles in that context, not errors |

