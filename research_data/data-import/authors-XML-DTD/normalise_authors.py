"""
normalise_authors.py
--------------------
Reads authors_with_qids.csv and applies the normalisation rules documented in
instructions.md.  Writes the result to authors_normalised.csv.

Normalisation steps applied
---------------------------
1. Strip leading/trailing whitespace from every field.
2. Normalise 'Country of Residence' to short-form names consistent with the
   'Citizenship' column:
     - 'United Kingdom (of Great Britain and Northern Ireland)'  ->  'UK'
     - 'United States of America'                               ->  'USA'
     - 'Russian Federation'                                     ->  'Russia'
     - 'United Republic of Tanzania'                            ->  'Tanzania'
3. Title-case 'Last Name' column (e.g. 'ALDUNCE' -> 'Aldunce',
   'VAN VUUREN' -> 'Van Vuuren', 'DIONGUE-NIANG' -> 'Diongue-Niang').
   Uses Python str.title() which correctly handles hyphens and accented chars.
4. Expand / clean 'Role' column:
     - 'CLA'              ->  'Coordinating Lead Author'
     - 'LA'               ->  'Lead Author'
     - 'RE'               ->  'Review Editor'
     - 'Core_Writing_Team'->  'Core Writing Team'
     - 'Lead' and 'Author' are retained as-is (WGII Cross-Chapter Papers).
5. Drop 'CountIfs' column (internal lookup count, not needed downstream).
6. Drop 'Chapter_Label' column (redundant with Chapter_QID_URL).
7. Drop 'Match_Type' column (QID match quality metadata, not needed for import).
8. Assign 'Author_ID' (e.g. AU0001) — one stable ID per unique author, shared
   across all their chapter rows, sorted alphabetically by Last Name then First Name.
9. Extract 'Chapter_QID' from 'Chapter_QID_URL' (e.g. 'Q190' from the full URL)
   and drop 'Chapter_QID_URL'.
10. Rename columns to underscore form and reorder:
      Author_ID, Last_Name, First_Name, Gender, Citizenship,
      Country_of_Residence, Affiliation, Report, Chapter, Chapter_QID, Role
"""

import csv
import os
import re

INPUT_CSV  = "authors_with_qids.csv"
OUTPUT_CSV = "authors_normalised.csv"

# Reference metadata added to every chapter contribution row (step 11)
SOURCE_URL    = "https://apps.ipcc.ch/report/authors/"
DATE_ACCESSED = "18 March 2026"

# Final output column order
OUT_FIELDS = [
    "ClimateKG_Author_ID",
    "Last_Name",
    "First_Name",
    "Gender",
    "Citizenship",
    "Country_of_Residence",
    "Affiliation",
    "Report",
    "Chapter",
    "Chapter_QID",
    "Role",
    "Source_URL",
    "Date_Accessed",
]

# Mapping for 'Role' normalisation (step 4)
ROLE_MAP = {
    "CLA":               "Coordinating Lead Author",
    "LA":                "Lead Author",
    "RE":                "Review Editor",
    "Core_Writing_Team": "Core Writing Team",
}

# Mapping for 'Country of Residence' normalisation (step 2)
COUNTRY_OF_RESIDENCE_MAP = {
    "United Kingdom (of Great Britain and Northern Ireland)": "UK",
    "United States of America": "USA",
    "Russian Federation": "Russia",
    "United Republic of Tanzania": "Tanzania",
}


def extract_qid(url: str) -> str:
    """Return the QID portion of a Wikibase entity URL (e.g. 'Q190')."""
    m = re.search(r'(Q\d+)$', url)
    return m.group(1) if m else url


def normalise_row(row: dict) -> tuple[dict, list[str]]:
    """Apply steps 1-9 to a single row. Returns (normalised_row, changes)."""
    changes = []
    out = {}

    # Step 1 – whitespace strip
    for key, value in row.items():
        if isinstance(value, str):
            stripped = value.strip()
            if stripped != value:
                changes.append(f"whitespace stripped from '{key}'")
            out[key] = stripped
        else:
            out[key] = value

    # Step 2 – Country of Residence
    cor = out.get("Country of Residence", "")
    if cor in COUNTRY_OF_RESIDENCE_MAP:
        new_val = COUNTRY_OF_RESIDENCE_MAP[cor]
        changes.append(f"Country of Residence: '{cor}' -> '{new_val}'")
        out["Country of Residence"] = new_val

    # Step 3 – Title-case Last Name
    last = out.get("Last Name", "")
    titled = last.title()
    if titled != last:
        changes.append(f"Last Name title-cased: '{last}' -> '{titled}'")
        out["Last Name"] = titled

    # Step 4 – Expand/clean Role
    role = out.get("Role", "")
    if role in ROLE_MAP:
        new_role = ROLE_MAP[role]
        changes.append(f"Role: '{role}' -> '{new_role}'")
        out["Role"] = new_role

    # Step 9 – Extract Chapter_QID from URL
    url = out.get("Chapter_QID_URL", "")
    qid = extract_qid(url)
    if qid != url:
        changes.append(f"Chapter_QID extracted: '{url}' -> '{qid}'")
    out["Chapter_QID"] = qid

    return out, changes


def build_author_id_map(rows: list[dict]) -> dict[tuple, str]:
    """
    Return a mapping of (Last Name, First Name) -> Author_ID.
    IDs are assigned alphabetically by Last Name then First Name.
    """
    unique = sorted(set((r["Last Name"].title(), r["First Name"]) for r in rows))
    return {author: f"AU{i+1:04d}" for i, author in enumerate(unique)}


def main():
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    input_path  = os.path.join(script_dir, INPUT_CSV)
    output_path = os.path.join(script_dir, OUTPUT_CSV)

    stats = {
        "total": 0,
        "whitespace_stripped": 0,
        "country_normalised": 0,
        "lastname_titlecased": 0,
        "role_normalised": 0,
    }
    role_counts: dict[str, int] = {}
    country_counts: dict[str, int] = {}

    # Read all rows first so we can assign Author_IDs (step 8)
    with open(input_path, newline="", encoding="utf-8") as fin:
        raw_rows = list(csv.DictReader(fin))

    # Apply per-row normalisation (steps 1-4, 9) to get title-cased names
    # before building the ID map
    pre_rows = []
    for raw_row in raw_rows:
        norm_row, _ = normalise_row(dict(raw_row))
        pre_rows.append(norm_row)

    # Step 8 – build Author_ID map
    author_id_map = build_author_id_map(pre_rows)

    with open(output_path, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for raw_row, norm_row in zip(raw_rows, pre_rows):
            stats["total"] += 1

            # Collect change stats
            _, changes = normalise_row(dict(raw_row))
            for change in changes:
                if "whitespace" in change:
                    stats["whitespace_stripped"] += 1
                elif "Country of Residence" in change:
                    stats["country_normalised"] += 1
                    orig = raw_row.get("Country of Residence", "")
                    country_counts[orig] = country_counts.get(orig, 0) + 1
                elif "Last Name title-cased" in change:
                    stats["lastname_titlecased"] += 1
                elif change.startswith("Role:"):
                    stats["role_normalised"] += 1
                    orig_role = raw_row.get("Role", "")
                    role_counts[orig_role] = role_counts.get(orig_role, 0) + 1

            # Step 8 – assign Author_ID
            author_key = (norm_row["Last Name"].title(), norm_row["First Name"])
            author_id = author_id_map[author_key]

            # Step 10 – rename and reorder into final output structure
            # Step 11 – add source reference fields
            out_row = {
                "ClimateKG_Author_ID":  author_id,
                "Last_Name":           norm_row["Last Name"],
                "First_Name":          norm_row["First Name"],
                "Gender":              norm_row["Gender"],
                "Citizenship":         norm_row["Citizenship"],
                "Country_of_Residence": norm_row["Country of Residence"],
                "Affiliation":         norm_row["Affiliation"],
                "Report":              norm_row["Report"],
                "Chapter":             norm_row["Chapter"],
                "Chapter_QID":         norm_row["Chapter_QID"],
                "Role":                norm_row["Role"],
                "Source_URL":          SOURCE_URL,
                "Date_Accessed":       DATE_ACCESSED,
            }
            writer.writerow(out_row)

    unique_authors = len(author_id_map)
    print(f"Processed {stats['total']} rows  ->  {output_path}")
    print(f"  Unique authors         : {unique_authors}  (IDs AU0001-AU{unique_authors:04d})")
    print(f"  Whitespace stripped    : {stats['whitespace_stripped']} fields")
    print(f"  Country of Residence   : {stats['country_normalised']} rows normalised")
    for orig in sorted(country_counts):
        new = COUNTRY_OF_RESIDENCE_MAP[orig]
        print(f"      '{orig}' -> '{new}' ({country_counts[orig]} rows)")
    print(f"  Last Name title-cased  : {stats['lastname_titlecased']} rows")
    print(f"  Role normalised        : {stats['role_normalised']} rows")
    for orig in sorted(role_counts):
        new = ROLE_MAP[orig]
        print(f"      '{orig}' -> '{new}' ({role_counts[orig]} rows)")


if __name__ == "__main__":
    main()
