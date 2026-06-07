"""
Add reference import columns to series_chapters.csv:
  Reference: Provider, Reference: URL, Reference: Date Accessed
"""
import csv
from datetime import date

CSV = "series_chapters.csv"
DATE_ACCESSED = date.today().isoformat()  # 2026-06-01
PROVIDER = "Crossref"

NEW_COLS = [
    "Reference: Provider",
    "Reference: URL",
    "Reference: Date Accessed",
]

with open(CSV, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

fieldnames = list(rows[0].keys()) + NEW_COLS

for row in rows:
    doi = row.get("DOI", "").strip()
    row["Reference: Provider"] = PROVIDER if doi else ""
    row["Reference: URL"] = f"https://doi.org/{doi}" if doi else ""
    row["Reference: Date Accessed"] = DATE_ACCESSED if doi else ""

with open(CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. {len(rows)} rows updated.")
