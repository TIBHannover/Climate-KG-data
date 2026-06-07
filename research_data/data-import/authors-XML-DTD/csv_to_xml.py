#!/usr/bin/env python3
"""
csv_to_xml.py
-------------
Reads authors_normalised.csv and produces outputs/authors.xml, validated
against authors.dtd.

Each unique author (grouped by Author_ID) becomes one <author> element.
Their chapter contributions become nested <contribution> elements, with
<role> as a child so it can be used as a Wikibase qualifier.

Usage
-----
  python csv_to_xml.py
"""

import csv
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from xml.dom import minidom

SCRIPT_DIR   = Path(__file__).parent
INPUT_CSV    = SCRIPT_DIR / "authors_normalised.csv"
OUTPUT_XML   = SCRIPT_DIR / "outputs" / "authors.xml"
DTD_FILENAME = "authors.dtd"   # relative reference kept in XML DOCTYPE


def _text_el(tag: str, text: str) -> ET.Element:
    el = ET.Element(tag)
    el.text = text
    return el


def build_xml(authors: dict[str, list[dict]]) -> ET.Element:
    """
    Build the ElementTree from the grouped author data.

    authors : {author_id: [row, row, ...]}  (rows share same bio fields)
    """
    root = ET.Element("ipcc-authors")

    for author_id in sorted(authors):
        rows = authors[author_id]
        # All rows for one author share the same bio fields; use first row.
        bio = rows[0]

        author_el = ET.SubElement(root, "author", id=author_id)
        author_el.append(_text_el("climatkg_author_id", author_id))
        author_el.append(_text_el("last_name",           bio["Last_Name"]))
        author_el.append(_text_el("first_name",          bio["First_Name"]))

        if bio.get("Gender"):
            author_el.append(_text_el("gender", bio["Gender"]))
        if bio.get("Citizenship"):
            author_el.append(_text_el("citizenship", bio["Citizenship"]))
        if bio.get("Country_of_Residence"):
            author_el.append(_text_el("country_of_residence", bio["Country_of_Residence"]))
        if bio.get("Affiliation"):
            author_el.append(_text_el("affiliation", bio["Affiliation"]))

        contribs_el = ET.SubElement(author_el, "chapter_contributions")
        for row in rows:
            contrib_el = ET.SubElement(
                contribs_el,
                "contribution",
                chapter_qid=row["Chapter_QID"],
                report=row["Report"],
                chapter=row["Chapter"],
            )
            contrib_el.append(_text_el("role",         row["Role"]))
            contrib_el.append(_text_el("source_url",    row["Source_URL"]))
            contrib_el.append(_text_el("date_accessed", row["Date_Accessed"]))

    return root


def prettify(root: ET.Element, dtd_filename: str) -> str:
    """Return a pretty-printed XML string with XML declaration and DOCTYPE."""
    raw = ET.tostring(root, encoding="unicode")
    dom = minidom.parseString(raw)
    pretty = dom.toprettyxml(indent="  ", encoding=None)

    # Replace the auto-generated declaration and insert our own + DOCTYPE
    lines = pretty.splitlines()
    # Drop minidom's <?xml ...?> line (first line)
    body = "\n".join(lines[1:])

    header = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<!DOCTYPE ipcc-authors PUBLIC "" "{dtd_filename}"[]>\n'
    )
    return header + body


def main() -> None:
    OUTPUT_XML.parent.mkdir(parents=True, exist_ok=True)

    # Read CSV
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Group by Author_ID
    authors: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        authors[row["ClimateKG_Author_ID"]].append(row)

    root = build_xml(authors)
    xml_str = prettify(root, DTD_FILENAME)

    with open(OUTPUT_XML, "w", encoding="utf-8") as f:
        f.write(xml_str)

    n_authors = len(authors)
    n_contribs = sum(len(v) for v in authors.values())
    print(f"Written {OUTPUT_XML}")
    print(f"  Authors         : {n_authors}")
    print(f"  Contributions   : {n_contribs}")


if __name__ == "__main__":
    main()
