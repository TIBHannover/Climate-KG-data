#!/usr/bin/env python3
"""
csv_to_enrichment_xml.py  --  Generate outputs/enrichment.xml from series_chapters.csv.

Reads series_chapters.csv (95 rows: 7 Series Q4 + 88 Chapters Q6) and produces
a DTD-conformant XML file validated against bibliographic-enrichment.dtd.

The XML is consumed by import_doi_enrichment.py to add DOI-sourced property
statements to existing Wikibase items.

Properties encoded per type
----------------------------
  Both Series and Chapter rows:
    Publisher (DOI)        string
    ISBN Electronic (DOI)  string
    ISBN Print (DOI)       string

  Series rows only (non-empty fields):
    Licence URL (DOI)      url
    Abstract (DOI)         string

Each statement gets a reference block:
    P17  reference URL    = "Reference: URL" column
    P18  date accessed    = "Reference: Date Accessed" column  (YYYY-MM-DD)
    P19  source version   = "Reference: Provider" column       (e.g. Crossref)

Usage
-----
  python csv_to_enrichment_xml.py
"""

import csv
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
INPUT_CSV   = BASE_DIR / "series_chapters.csv"
OUTPUT_XML  = BASE_DIR / "outputs" / "enrichment.xml"
DTD_FILE    = "bibliographic-enrichment.dtd"   # relative ref in XML DOCTYPE

# ---------------------------------------------------------------------------
# Property definitions
# (label, CSV column, datatype, include_for)
# include_for: "both" | "Series"
# ---------------------------------------------------------------------------
PROPERTY_DEFS = [
    ("Publisher (DOI)",        "Publisher (DOI)",        "string", "both"),
    ("ISBN Electronic (DOI)",  "ISBN Electronic (DOI)",  "string", "both"),
    ("ISBN Print (DOI)",       "ISBN Print (DOI)",        "string", "both"),
    ("Licence URL (DOI)",      "Licence URL (DOI)",       "url",    "Series"),
    ("Abstract (DOI)",         "Abstract (DOI)",          "string", "Series"),
]

# Reference property PIDs (already exist in Wikibase, not created by bootstrap)
P_REFERENCE_URL   = "P17"
P_DATE_ACCESSED   = "P18"
P_SOURCE_VERSION  = "P19"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_jats(text: str) -> str:
    """Remove JATS/XML markup tags that Crossref sometimes includes in abstracts."""
    if not text:
        return text
    cleaned = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple whitespace runs introduced by tag removal
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _build_reference(ref_url: str, date_accessed: str, provider: str) -> ET.Element:
    """Build a <reference> element with P17, P18, P19 snaks."""
    ref_el = ET.Element("reference")
    r1 = ET.SubElement(ref_el, "ref", pid=P_REFERENCE_URL,  value=ref_url)       # noqa: F841
    r2 = ET.SubElement(ref_el, "ref", pid=P_DATE_ACCESSED,  value=date_accessed)  # noqa: F841
    r3 = ET.SubElement(ref_el, "ref", pid=P_SOURCE_VERSION, value=provider)       # noqa: F841
    return ref_el


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Add pretty-print indentation to an ElementTree in-place."""
    pad = "\n" + "  " * level
    child_pad = "\n" + "  " * (level + 1)
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = child_pad
        if not elem.tail or not elem.tail.strip():
            elem.tail = pad
        for child in elem:
            _indent(child, level + 1)
        # Last child's tail should align with parent close tag
        if not child.tail or not child.tail.strip():  # type: ignore[possibly-undefined]
            child.tail = pad                           # type: ignore[possibly-undefined]
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = pad


# ---------------------------------------------------------------------------
# XML builder
# ---------------------------------------------------------------------------

def build_xml(rows: list[dict]) -> ET.Element:
    """Build the full <bibliographic-enrichment> element tree."""
    root = ET.Element(
        "bibliographic-enrichment",
        generated=date.today().isoformat(),
    )

    skipped = 0
    for row in rows:
        item_type = row["Type"]       # "Series" or "Chapter"
        qid       = row["QID"]
        label     = row["Label"]

        ref_url       = row["Reference: URL"]
        date_accessed = row["Reference: Date Accessed"]
        provider      = row["Reference: Provider"]

        # Collect statements for this item
        statements: list[tuple[str, str, str]] = []  # (prop_label, datatype, value)

        for prop_label, csv_col, datatype, include_for in PROPERTY_DEFS:
            if include_for == "Series" and item_type != "Series":
                continue
            raw_value = row.get(csv_col, "").strip()
            if not raw_value:
                continue
            # Clean up abstract text (may contain JATS XML from Crossref)
            if csv_col == "Abstract (DOI)":
                raw_value = _strip_jats(raw_value)
            if raw_value:
                statements.append((prop_label, datatype, raw_value))

        if not statements:
            skipped += 1
            continue

        item_el = ET.SubElement(root, "item", qid=qid, type=item_type, label=label)

        for prop_label, datatype, value in statements:
            stmt_el = ET.SubElement(
                item_el, "statement",
                prop=prop_label,
                datatype=datatype,
                value=value,
            )
            stmt_el.append(_build_reference(ref_url, date_accessed, provider))

    print(f"Built XML for {len(rows) - skipped} items ({skipped} skipped - no data).")
    return root


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Input CSV not found: {INPUT_CSV}")

    with open(INPUT_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    print(f"Read {len(rows)} rows from {INPUT_CSV.name}")

    root = build_xml(rows)
    _indent(root)

    OUTPUT_XML.parent.mkdir(exist_ok=True)

    # Write with DOCTYPE declaration referencing the DTD
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype_decl    = f'<!DOCTYPE bibliographic-enrichment SYSTEM "{DTD_FILE}">\n'

    xml_body = ET.tostring(root, encoding="unicode")
    full_output = xml_declaration + doctype_decl + xml_body + "\n"

    OUTPUT_XML.write_text(full_output, encoding="utf-8")
    print(f"XML written to: {OUTPUT_XML}")

    # Summary
    items    = root.findall("item")
    series   = [i for i in items if i.get("type") == "Series"]
    chapters = [i for i in items if i.get("type") == "Chapter"]
    stmts    = root.findall(".//statement")
    print(f"  {len(items)} items  ({len(series)} Series, {len(chapters)} Chapters)")
    print(f"  {len(stmts)} statements total")


if __name__ == "__main__":
    main()
