#!/usr/bin/env python3
"""
normalise_refs.py  —  Normalise the IPCC AR6 bibliographic reference source CSV.

Input  : references-source.csv
Output : references_normalised.csv

Normalisation steps applied
----------------------------
1.  Whitespace stripping      — strip leading/trailing whitespace from all fields.
2.  Year                      — validate 4-digit integer; log and skip malformed rows.
3.  DOI                       — strip protocol prefix if present
                                (e.g. "https://doi.org/10.1000/x" -> "10.1000/x").
4.  Publication_Type          — expand/standardise to lowercase snake_case:
                                "Journal Article" -> "article", "Book Chapter" -> "book_chapter",
                                "Technical Report" -> "report", etc.
5.  Authors                   — normalise separator to "; " (semicolon-space).
6.  ClimateKG_Ref_ID          — assign stable REF0001...REFnnnn per unique reference,
                                sorted alphabetically by Citation_Key then Year.
                                Same ID appears on all rows for the same reference.
7.  Chapter_QID               — extract QID from URL if column contains full URL.
8.  Source_URL / Date_Accessed — add constant provenance columns.
9.  Column rename and reorder — standardise headers; drop internal columns.

TODO: Update steps once source data format is confirmed.
"""

import csv
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
INPUT_FILE  = Path(__file__).parent / "references-source.csv"
OUTPUT_FILE = Path(__file__).parent / "references_normalised.csv"

SOURCE_URL    = "https://apps.ipcc.ch/report/references/"   # TODO: confirm actual URL
DATE_ACCESSED = "18 March 2026"                              # TODO: update when re-run

OUT_FIELDS = [
    "ClimateKG_Ref_ID",
    "Citation_Key",
    "Authors",
    "Year",
    "Title",
    "Publication_Type",
    "Source",
    "Volume",
    "Issue",
    "Pages",
    "DOI",
    "URL",
    "Report",
    "Chapter",
    "Chapter_QID",
    "Source_URL",
    "Date_Accessed",
]

# Mapping from raw publication type values to normalised form.
# TODO: populate once source data types are known.
PUBLICATION_TYPE_MAP = {
    "journal article":   "article",
    "article":           "article",
    "book":              "book",
    "book chapter":      "book_chapter",
    "chapter":           "book_chapter",
    "technical report":  "report",
    "report":            "report",
    "thesis":            "thesis",
    "other":             "other",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_doi_prefix(doi: str) -> str:
    """Remove https://doi.org/ or http://dx.doi.org/ prefix from DOI."""
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/"):
        if doi.lower().startswith(prefix):
            return doi[len(prefix):]
    return doi


def normalise_pub_type(raw: str) -> str:
    """Normalise publication type to lowercase snake_case."""
    return PUBLICATION_TYPE_MAP.get(raw.strip().lower(), raw.strip().lower())


def extract_qid(value: str) -> str:
    """Extract a QID (e.g. Q190) from a full URL or return the value as-is."""
    match = re.search(r"(Q\d+)$", value.strip())
    return match.group(1) if match else value.strip()


def assign_ref_ids(rows: list[dict]) -> dict[str, str]:
    """
    Assign stable ClimateKG_Ref_ID values (REF0001...) to unique references.
    Uniqueness is determined by Citation_Key + Year.
    Returns a mapping of (citation_key, year) -> ref_id.
    """
    seen: dict[tuple[str, str], str] = {}
    # Collect unique (citation_key, year) pairs, sorted for stable assignment.
    unique_keys = sorted(
        {(r.get("Citation_Key", "").strip(), r.get("Year", "").strip()) for r in rows}
    )
    for idx, key in enumerate(unique_keys, start=1):
        seen[key] = f"REF{idx:04d}"
    return seen


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_FILE.exists():
        sys.exit(
            f"Input file not found: {INPUT_FILE}\n"
            "Add references-source.csv to this directory and re-run."
        )

    with INPUT_FILE.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        raw_rows = list(reader)

    print(f"Read {len(raw_rows)} rows from {INPUT_FILE.name}")

    # ── Step 1: whitespace strip ──────────────────────────────────────────
    for row in raw_rows:
        for k in row:
            if isinstance(row[k], str):
                row[k] = row[k].strip()

    # ── Step 6: assign stable reference IDs ──────────────────────────────
    ref_id_map = assign_ref_ids(raw_rows)

    changed = 0
    out_rows = []

    for row in raw_rows:
        out_row: dict[str, str] = {}

        # ── Step 2: year validation ───────────────────────────────────────
        year = row.get("Year", "").strip()
        if year and not re.fullmatch(r"\d{4}", year):
            print(f"  [WARN] Skipping row with invalid year: {year!r} — {row.get('Citation_Key','')}")
            changed += 1
            continue

        # ── Step 3: DOI normalisation ─────────────────────────────────────
        doi = strip_doi_prefix(row.get("DOI", ""))

        # ── Step 4: publication type ──────────────────────────────────────
        pub_type = normalise_pub_type(row.get("Publication_Type", ""))

        # ── Step 5: authors separator ─────────────────────────────────────
        authors = re.sub(r"\s*[;,]\s*", "; ", row.get("Authors", "")).strip("; ")

        # ── Step 7: chapter QID ───────────────────────────────────────────
        chapter_qid = extract_qid(row.get("Chapter_QID", row.get("Chapter_QID_URL", "")))

        # ── Step 6: assign ref ID ─────────────────────────────────────────
        key = (row.get("Citation_Key", "").strip(), year)
        ref_id = ref_id_map.get(key, "")

        # ── Step 8-9: build output row ────────────────────────────────────
        out_row = {
            "ClimateKG_Ref_ID":   ref_id,
            "Citation_Key":        row.get("Citation_Key", ""),
            "Authors":             authors,
            "Year":                year,
            "Title":               row.get("Title", ""),
            "Publication_Type":    pub_type,
            "Source":              row.get("Source", ""),
            "Volume":              row.get("Volume", ""),
            "Issue":               row.get("Issue", ""),
            "Pages":               row.get("Pages", ""),
            "DOI":                 doi,
            "URL":                 row.get("URL", ""),
            "Report":              row.get("Report", ""),
            "Chapter":             row.get("Chapter", ""),
            "Chapter_QID":         chapter_qid,
            "Source_URL":          SOURCE_URL,
            "Date_Accessed":       DATE_ACCESSED,
        }
        out_rows.append(out_row)

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(out_rows)

    unique_refs = len({r["ClimateKG_Ref_ID"] for r in out_rows})
    print(f"Wrote {len(out_rows)} rows ({unique_refs} unique references) to {OUTPUT_FILE.name}")
    if changed:
        print(f"  {changed} rows skipped or modified (see warnings above)")


if __name__ == "__main__":
    main()
