#!/usr/bin/env python3
"""
csv_to_xml.py  —  Convert references_normalised.csv to outputs/references.xml.

Reads references_normalised.csv and produces a DTD-conformant XML file
(validated against bibliographic.dtd) suitable for upload_to_wikibase.py.

Usage
-----
  python csv_to_xml.py
"""

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

INPUT_FILE  = Path(__file__).parent / "references_normalised.csv"
OUTPUT_FILE = Path(__file__).parent / "outputs" / "references.xml"
DTD_FILE    = Path(__file__).parent / "bibliographic.dtd"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_el(tag: str, text: str) -> ET.Element:
    """Create an XML element with text content, omitting if text is blank."""
    el = ET.Element(tag)
    el.text = text or ""
    return el


def build_xml(rows: list[dict]) -> ET.Element:
    """
    Build the <bibliographic-references> element tree from normalised rows.

    Groups rows by ClimateKG_Ref_ID so that each unique reference becomes
    one <reference> element with one <citation> per citing chapter.
    """
    # Group rows by ref ID (preserving insertion order = sorted REF0001...)
    refs: dict[str, list[dict]] = {}
    for row in rows:
        ref_id = row["ClimateKG_Ref_ID"]
        refs.setdefault(ref_id, []).append(row)

    root = ET.Element("bibliographic-references")

    for ref_id, ref_rows in refs.items():
        first = ref_rows[0]  # bibliographic fields are the same on every row

        ref_el = ET.SubElement(root, "reference", id=ref_id)

        ref_el.append(_text_el("climatkg_ref_id",   first["ClimateKG_Ref_ID"]))
        ref_el.append(_text_el("citation_key",       first["Citation_Key"]))
        ref_el.append(_text_el("authors",            first["Authors"]))
        ref_el.append(_text_el("year",               first["Year"]))
        ref_el.append(_text_el("title",              first["Title"]))
        ref_el.append(_text_el("publication_type",   first["Publication_Type"]))

        # Optional elements — only include if non-blank
        for tag, field in [
            ("source",  "Source"),
            ("volume",  "Volume"),
            ("issue",   "Issue"),
            ("pages",   "Pages"),
            ("doi",     "DOI"),
            ("url",     "URL"),
        ]:
            if first.get(field, "").strip():
                ref_el.append(_text_el(tag, first[field]))

        # Citations — one per chapter that cites this reference
        citations_el = ET.SubElement(ref_el, "citations")
        for row in ref_rows:
            if not row.get("Chapter_QID", "").strip():
                continue
            cit_el = ET.SubElement(
                citations_el,
                "citation",
                chapter_qid=row["Chapter_QID"],
                report=row["Report"],
                chapter=row["Chapter"],
            )
            cit_el.append(_text_el("source_url",    row["Source_URL"]))
            cit_el.append(_text_el("date_accessed", row["Date_Accessed"]))

    return root


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}\n"
            "Run normalise_refs.py first."
        )

    with INPUT_FILE.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    print(f"Read {len(rows)} rows from {INPUT_FILE.name}")

    root = build_xml(rows)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    # Write with XML declaration and DTD DOCTYPE
    with OUTPUT_FILE.open("wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write(f'<!DOCTYPE bibliographic-references SYSTEM "{DTD_FILE.name}">\n'.encode())
        tree.write(fh, encoding="unicode", xml_declaration=False)

    unique_refs = len({r["ClimateKG_Ref_ID"] for r in rows})
    print(f"Wrote {unique_refs} references ({len(rows)} citations) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
