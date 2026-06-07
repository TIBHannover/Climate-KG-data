#!/usr/bin/env python3
"""
fetch_series_chapters.py — Export Series and Chapter items from LOCAL Wikibase.

Queries for all items that are instance of:
  Q4  — Series   (7 items expected)
  Q6  — Chapter  (87 items expected)

Fields exported per item:
  Type         — Series | Chapter
  QID          — e.g. Q77
  Label        — English label
  Description  — English description (blank if none)
  Acronym      — extracted from skos:altLabel (IPCC_AR6_WGI -> WGI); blank if absent
  DOI          — P10 value; blank if absent

Output: series_chapters.csv  (same folder as this script)

Usage:
  python fetch_series_chapters.py
"""

import csv
import os
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SPARQL_URL   = os.getenv("SPARQL_URL",   "http://localhost:9999/bigdata/sparql")
WIKIBASE_URL = os.getenv("WIKIBASE_URL", "http://localhost:8080")

ENTITY_BASE = WIKIBASE_URL + "/entity/"
PROP_BASE   = WIKIBASE_URL + "/prop/direct/"

SERIES_CLASS  = "Q4"
CHAPTER_CLASS = "Q6"
P_DOI         = "P10"

OUTPUT_PATH = Path(__file__).parent / "series_chapters.csv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sparql_query(sparql_text: str) -> list[dict]:
    """POST a SPARQL SELECT query and return list of binding dicts."""
    resp = requests.post(
        SPARQL_URL,
        data={"query": sparql_text, "format": "json"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def extract_acronym(aliases: list[str]) -> str:
    """
    Pick the most specific IPCC_AR6 alias and return its code suffix.

    Aliases may be stored as a single compound string, e.g.:
      "IPCC_AR6; IPCC_AR6_WGI"
    or as individual strings.

    Examples:
      ["IPCC_AR6; IPCC_AR6_WGI"]         -> "WGI"
      ["IPCC_AR6", "IPCC_AR6_WGI_CH01"]  -> "WGI_CH01"
      []                                  -> ""
    """
    # Expand any compound aliases ("; " separated)
    tokens: list[str] = []
    for a in aliases:
        tokens.extend(t.strip() for t in a.split(";"))

    # Keep only IPCC_AR6_* tokens (exclude bare "IPCC_AR6")
    coded = [t for t in tokens if t.startswith("IPCC_AR6_")]
    if not coded:
        return ""
    # Choose the longest (most specific) token
    best = max(coded, key=len)
    return best[len("IPCC_AR6_"):]


# ---------------------------------------------------------------------------
# SPARQL queries
# ---------------------------------------------------------------------------

def fetch_items(class_qid: str) -> list[dict]:
    """
    Return a list of dicts with keys:
      qid, label, description, acronym, doi
    for all items that are instance of <class_qid>.
    """
    p1  = PROP_BASE + "P1"
    cls = ENTITY_BASE + class_qid
    doi_prop = PROP_BASE + P_DOI

    query = (
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n"
        "PREFIX schema: <http://schema.org/>\n"
        "\n"
        "SELECT DISTINCT ?item ?label ?description ?alias ?doi WHERE {\n"
        "  ?item <" + p1 + "> <" + cls + "> .\n"
        "  ?item rdfs:label ?label . FILTER(lang(?label) = 'en')\n"
        "  OPTIONAL { ?item schema:description ?description . FILTER(lang(?description) = 'en') }\n"
        "  OPTIONAL { ?item skos:altLabel ?alias .             FILTER(lang(?alias)       = 'en') }\n"
        "  OPTIONAL { ?item <" + doi_prop + "> ?doi . }\n"
        "}\n"
        "ORDER BY ?item"
    )

    bindings = sparql_query(query)

    # Group rows by QID (multiple alias rows per item)
    items: dict[str, dict] = {}
    for b in bindings:
        qid   = b["item"]["value"].split("/")[-1]
        if qid not in items:
            items[qid] = {
                "qid":         qid,
                "label":       b["label"]["value"],
                "description": b.get("description", {}).get("value", ""),
                "aliases":     [],
                "doi":         b.get("doi", {}).get("value", ""),
            }
        alias = b.get("alias", {}).get("value", "")
        if alias and alias not in items[qid]["aliases"]:
            items[qid]["aliases"].append(alias)
        # DOI may appear on any row; keep first non-blank
        if not items[qid]["doi"]:
            items[qid]["doi"] = b.get("doi", {}).get("value", "")

    result = []
    for rec in items.values():
        result.append({
            "qid":         rec["qid"],
            "label":       rec["label"],
            "description": rec["description"],
            "acronym":     extract_acronym(rec["aliases"]),
            "doi":         rec["doi"],
        })

    # Sort by numeric QID
    result.sort(key=lambda r: int(r["qid"][1:]))
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Querying LOCAL Wikibase (" + WIKIBASE_URL + ") ...")

    series   = fetch_items(SERIES_CLASS)
    chapters = fetch_items(CHAPTER_CLASS)

    print(f"  Series   ({SERIES_CLASS}): {len(series):>4} items")
    print(f"  Chapters ({CHAPTER_CLASS}): {len(chapters):>4} items")

    rows = (
        [{"Type": "Series",  **r} for r in series] +
        [{"Type": "Chapter", **r} for r in chapters]
    )

    fieldnames = ["Type", "QID", "Label", "Description", "Acronym", "DOI"]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "Type":        row["Type"],
                "QID":         row["qid"],
                "Label":       row["label"],
                "Description": row["description"],
                "Acronym":     row["acronym"],
                "DOI":         row["doi"],
            })

    print(f"\nWrote {len(rows)} rows to: {OUTPUT_PATH}")
    print("\nSummary:")
    print(f"  Series:   {len(series)}")
    print(f"  Chapters: {len(chapters)}")
    print(f"  Total:    {len(rows)}")


if __name__ == "__main__":
    main()
