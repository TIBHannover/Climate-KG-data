"""
Enrich series_chapters.csv with bibliographic fields from CrossRef.
New columns added:
  Publisher (DOI), ISBN Electronic (DOI), ISBN Print (DOI)  -- for all rows
  Licence URL (DOI), Abstract (DOI)                         -- Series rows only
"""
import csv
import time
import requests

INPUT = "series_chapters.csv"
OUTPUT = "series_chapters.csv"
HEADERS = {"User-Agent": "ClimateKG/1.0 (mailto:admin@climatekg.org)"}

NEW_COLS = [
    "Publisher (DOI)",
    "ISBN Electronic (DOI)",
    "ISBN Print (DOI)",
    "Licence URL (DOI)",
    "Abstract (DOI)",
]


def fetch_crossref(doi):
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()["message"]
    except Exception as e:
        print(f"  ERROR fetching {doi}: {e}")
    return None


def extract_fields(msg, row_type):
    publisher = msg.get("publisher", "")

    isbns = {i["type"]: i["value"] for i in msg.get("isbn-type", [])}
    isbn_electronic = isbns.get("electronic", "")
    isbn_print = isbns.get("print", "")

    licence_url = ""
    abstract = ""
    if row_type == "Series":
        licences = msg.get("license", [])
        if licences:
            licence_url = licences[0].get("URL", "")
        abstract = msg.get("abstract", "")
        # Strip JATS XML tags if present
        import re
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()

    return publisher, isbn_electronic, isbn_print, licence_url, abstract


def main():
    with open(INPUT, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) + NEW_COLS

    enriched = []
    for i, row in enumerate(rows):
        doi = row.get("DOI", "").strip()
        print(f"[{i+1}/{len(rows)}] {row['QID']} {doi}")

        extras = {"Publisher (DOI)": "", "ISBN Electronic (DOI)": "",
                  "ISBN Print (DOI)": "", "Licence URL (DOI)": "", "Abstract (DOI)": ""}

        if doi:
            msg = fetch_crossref(doi)
            if msg:
                pub, isbn_e, isbn_p, lic, abst = extract_fields(msg, row["Type"])
                extras = {
                    "Publisher (DOI)": pub,
                    "ISBN Electronic (DOI)": isbn_e,
                    "ISBN Print (DOI)": isbn_p,
                    "Licence URL (DOI)": lic,
                    "Abstract (DOI)": abst,
                }
            time.sleep(0.5)  # polite rate limiting

        enriched.append({**row, **extras})

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched)

    print(f"\nDone. {len(enriched)} rows written to {OUTPUT}")


if __name__ == "__main__":
    main()
