"""
lookup_chapter_qids.py
----------------------
Reads authors.csv, looks up the Wikibase QID URL and label for each
(Report, Chapter) combination from the LOCAL Wikibase SPARQL endpoint, and
writes a new CSV (authors_with_qids.csv) with two columns prepended:
  Chapter_QID_URL  – e.g. http://localhost:8080/entity/Q21
  Chapter_Label    – e.g. Framing and Context

A Match_Type column is also appended for review:
  EXACT   – case-insensitive exact match
  FUZZY   – best fuzzy match above 0.70 similarity
  NO MATCH – no suitable match found
"""

import csv
import difflib
import re
import json
import urllib.request
import urllib.parse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SPARQL_ENDPOINT = "http://localhost:9999/bigdata/namespace/wdq/sparql"
BASE_URL        = "http://localhost:8080"
INPUT_CSV       = "authors.csv"
OUTPUT_CSV      = "authors_with_qids.csv"
FUZZY_CUTOFF    = 0.70

# Map CSV report codes to a distinctive keyword present in the Wikibase
# schema:description field on each chapter item.
REPORT_KEYWORDS = {
    "SYR":    "Synthesis Report",
    "WGI":    "Physical Science Basis",
    "WGII":   "Impacts, Adaptation and Vulnerability",
    "WGIII":  "Mitigation of Climate Change",
    "SR1.5":  "1.5",
    "SRCCL":  "Climate Change and Land",
    "SROCC":  "Ocean and Cryosphere",
}

# Short-hand chapter codes that map directly to Wikibase labels
SHORTHAND_MAP = {
    "SPM":   "Summary for Policymakers",
    "LR":    "Longer Report",
    "ATLAS": "Atlas",
    "TS":    "Technical Summary",
}

# ---------------------------------------------------------------------------
# SPARQL helper
# ---------------------------------------------------------------------------
def sparql_query(q):
    url = SPARQL_ENDPOINT + "?query=" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

# ---------------------------------------------------------------------------
# Load all chapters from Wikibase
# ---------------------------------------------------------------------------
def load_all_chapters():
    """Return list of dicts: {qid, url, label, label_lc, desc}"""
    result = sparql_query(f"""
PREFIX wd:     <{BASE_URL}/entity/>
PREFIX wdt:    <{BASE_URL}/prop/direct/>
PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>

SELECT ?item ?itemLabel ?desc WHERE {{
  ?item wdt:P1 wd:Q6 .
  ?item rdfs:label ?itemLabel .
  FILTER(LANG(?itemLabel) = "en")
  OPTIONAL {{ ?item schema:description ?desc . FILTER(LANG(?desc) = "en") }}
}}
""")
    chapters = []
    for b in result["results"]["bindings"]:
        qid   = b["item"]["value"].split("/")[-1]
        label = b["itemLabel"]["value"]
        desc  = b.get("desc", {}).get("value", "")
        chapters.append({
            "qid":      qid,
            "url":      f"{BASE_URL}/entity/{qid}",
            "label":    label,
            "label_lc": label.lower(),
            "desc":     desc,
        })
    return chapters

# ---------------------------------------------------------------------------
# Normalise a CSV chapter name to a searchable title
# ---------------------------------------------------------------------------
def normalise_chapter(raw):
    """Strip leading 'Chapter N:' or 'Cross-Chapter Paper:' prefix;
    expand known shorthand codes."""
    raw = raw.strip()

    # Shorthand codes (case-insensitive)
    if raw.upper() in SHORTHAND_MAP:
        return SHORTHAND_MAP[raw.upper()]

    # "Chapter 1: Title"  or  "Chapter 1a: Title"
    m = re.match(r'^Chapter\s+[\dA-Za-z]+\s*:\s*(.+)$', raw, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # "Cross-Chapter Paper: Title"
    m2 = re.match(r'^Cross-Chapter Paper\s*:\s*(.+)$', raw, re.IGNORECASE)
    if m2:
        return m2.group(1).strip()

    return raw

# ---------------------------------------------------------------------------
# Match a (report_code, chapter_name) pair to a Wikibase chapter
# ---------------------------------------------------------------------------
def find_chapter(chapters, report_code, raw_chapter):
    if not raw_chapter.strip() or raw_chapter.strip() in (":", "Chapter :"):
        return "", "", "EMPTY"

    keyword = REPORT_KEYWORDS.get(report_code, "")

    # Filter to chapters belonging to this report
    report_chapters = [c for c in chapters if keyword and keyword.lower() in c["desc"].lower()]
    # Fall back to all chapters if nothing filtered (unknown report code)
    pool = report_chapters if report_chapters else chapters

    search = normalise_chapter(raw_chapter).lower()

    # 1. Exact case-insensitive match within filtered pool
    for c in pool:
        if c["label_lc"] == search:
            return c["url"], c["label"], "EXACT"

    # 2. Fuzzy match within filtered pool
    pool_labels_lc = [c["label_lc"] for c in pool]
    close = difflib.get_close_matches(search, pool_labels_lc, n=1, cutoff=FUZZY_CUTOFF)
    if close:
        for c in pool:
            if c["label_lc"] == close[0]:
                return c["url"], c["label"], f"FUZZY({round(difflib.SequenceMatcher(None, search, close[0]).ratio(), 2)})"

    return "", "", f"NO MATCH ({search!r})"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path  = os.path.join(script_dir, INPUT_CSV)
    output_path = os.path.join(script_dir, OUTPUT_CSV)

    print("Loading chapters from Wikibase SPARQL …")
    chapters = load_all_chapters()
    print(f"  Loaded {len(chapters)} chapter items.")

    stats = {"EXACT": 0, "FUZZY": 0, "NO MATCH": 0, "EMPTY": 0}

    with open(input_path, newline="", encoding="utf-8") as fin, \
         open(output_path, "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin)
        fieldnames = ["Chapter_QID_URL", "Chapter_Label"] + reader.fieldnames + ["Match_Type"]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        # Cache lookups so we only hit SPARQL once per unique (Report, Chapter)
        cache = {}
        row_count = 0
        for row in reader:
            row_count += 1
            key = (row["Report"].strip(), row["Chapter"].strip())
            if key not in cache:
                cache[key] = find_chapter(chapters, key[0], key[1])
            qid_url, label, match_type = cache[key]

            # Accumulate stats by category
            cat = "NO MATCH" if match_type.startswith("NO MATCH") else \
                  "FUZZY"    if match_type.startswith("FUZZY")    else match_type
            stats[cat] = stats.get(cat, 0) + 1

            out = {"Chapter_QID_URL": qid_url, "Chapter_Label": label,
                   "Match_Type": match_type}
            out.update(row)
            writer.writerow(out)

    print(f"\nProcessed {row_count} rows  →  {output_path}")
    print(f"  EXACT    : {stats.get('EXACT', 0)}")
    print(f"  FUZZY    : {stats.get('FUZZY', 0)}")
    print(f"  NO MATCH : {stats.get('NO MATCH', 0)}")
    print(f"  EMPTY    : {stats.get('EMPTY', 0)}")
    if stats.get("NO MATCH", 0) or stats.get("EMPTY", 0):
        print("\nUnmatched (Report, Chapter) pairs:")
        seen = set()
        import sys
        for (rep, ch), (url, lbl, mt) in cache.items():
            if (mt.startswith("NO MATCH") or mt == "EMPTY") and (rep, ch) not in seen:
                seen.add((rep, ch))
                print(f"  [{rep}]  {ch!r}  →  {mt}")

if __name__ == "__main__":
    main()
