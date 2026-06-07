#!/usr/bin/env python3
"""
upload_to_wikibase.py  —  Import IPCC AR6 Acronyms into a Wikibase instance.

Workflow
--------
1. First run (no ACRONYM_ITEM_QID set):
   - Creates an "Acronym" class item in Wikibase if it doesn't exist.
   - Prints its QID, then exits.
   Add  ACRONYM_ITEM_QID=Q<n>  to .env and re-run.

2. Second run (ACRONYM_ITEM_QID set):
   - Parses ipccacronyms.xml and uploads one Wikibase item per acronym.

Each uploaded item has:
  Label       : acronym code  (e.g. "AFOLU")
  Description : "Acronym for: <first description text>"
  instance of (P1)  → ACRONYM_ITEM_QID
      qualifier  P19 (source version) = "IPCC AR6"
  Part of     (P3)  → one statement per report (QID from REPORT_QIDS map)
  Definition  (P13) → one statement per <description> element
      qualifier  P19 (source version) = "IPCC AR6"

Usage
-----
  python upload_to_wikibase.py              # full upload
  DRY_RUN=true python upload_to_wikibase.py # dry run, no writes
  LIMIT=10 python upload_to_wikibase.py     # process first 10 items only
"""

import os
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Optional .env loading ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent
    while _env_path != _env_path.parent:
        if (_env_path / ".env").exists():
            load_dotenv(_env_path / ".env")
            break
        _env_path = _env_path.parent
except ImportError:
    pass

try:
    from wikibaseintegrator import WikibaseIntegrator, wbi_login
    from wikibaseintegrator.wbi_config import config as wbi_config
    from wikibaseintegrator import datatypes as wbi_datatypes
    from wikibaseintegrator.models import Qualifiers
except ImportError:
    sys.exit(
        "wikibaseintegrator not found.\n"
        "Install it with:  pip install wikibaseintegrator\n"
    )

# ── Configuration ──────────────────────────────────────────────────────────────

WIKIBASE_URL = os.getenv("WIKIBASE_URL", "http://localhost:8080")
MW_API_URL   = os.getenv("MW_API_URL",   f"{WIKIBASE_URL}/api.php")
SPARQL_URL   = os.getenv("SPARQL_URL",   "http://localhost:9999/bigdata/sparql")
WB_USER      = os.getenv("WB_USER",      "admin")
WB_PASSWORD  = os.getenv("WB_PASSWORD",  "")

# Property IDs — hard-coded from the established Wikibase schema.
PROP_INSTANCE_OF = "P1"   # wikibase-item
PROP_PART_OF     = "P3"   # wikibase-item
PROP_DEFINITION  = "P13"  # monolingualtext
PROP_SOURCE_VER  = "P19"  # string  ("source version" — used as qualifier)

# QID of the "Acronym" class item.  Set via .env or environment variable.
# Left blank on first run; the script will create the item and print its QID.
ACRONYM_ITEM_QID = os.getenv("ACRONYM_ITEM_QID", "")

# Qualifier value used throughout ("IPCC AR6").
SOURCE_QUALIFIER = "IPCC AR6"

# AR6 report code → Wikibase QID  (from instructions.md)
REPORT_QIDS: dict[str, str] = {
    "SR1.5": "Q10",
    "SRCCL": "Q35",
    "SROCC": "Q57",
    "SYR":   "Q189",
    "WGI":   "Q77",
    "WGII":  "Q106",
    "WGIII": "Q150",
}

XML_PATH = Path(__file__).parent / "ipccacronyms.xml"
LOG_PATH = Path(__file__).parent / "outputs" / "upload_log.json"

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
OFFSET  = int(os.getenv("OFFSET", "0"))  # skip first N items
LIMIT   = int(os.getenv("LIMIT", "0"))   # 0 = no limit


# ── Wikibase connection ────────────────────────────────────────────────────────

def connect() -> WikibaseIntegrator:
    wbi_config["MEDIAWIKI_API_URL"]   = MW_API_URL
    wbi_config["SPARQL_ENDPOINT_URL"] = SPARQL_URL
    wbi_config["WIKIBASE_URL"]        = WIKIBASE_URL
    login = wbi_login.Login(user=WB_USER, password=WB_PASSWORD)
    return WikibaseIntegrator(login=login)


# ── Acronym class item ─────────────────────────────────────────────────────────

def ensure_acronym_class(wbi: WikibaseIntegrator) -> str:
    """Create the 'Acronym' class item if it doesn't exist. Return its QID."""
    item = wbi.item.new()
    item.labels.set(language="en", value="Acronym")
    item.descriptions.set(language="en", value="IPCC AR6 acronym")
    if DRY_RUN:
        print("[DRY RUN] Would create 'Acronym' class item.")
        return "Q_DRY"
    result = item.write()
    return result.id


# ── XML parsing ────────────────────────────────────────────────────────────────

def parse_xml(xml_path: Path) -> list[dict]:
    """Parse ipccacronyms.xml; return list of acronym dicts."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    acronyms = []
    for acr_el in root.findall("acronym"):
        code = (acr_el.findtext("code") or "").strip()
        descriptions = []
        for d in acr_el.findall(".//description"):
            text = (d.text or "").strip()
            source = (d.get("source") or "").strip()
            if text:
                descriptions.append({"text": text, "source": source})
        reports = [
            (r.text or "").strip()
            for r in acr_el.findall(".//report")
            if (r.text or "").strip()
        ]
        acronyms.append({
            "id":           acr_el.get("id"),
            "code":         code,
            "descriptions": descriptions,
            "reports":      reports,
        })
    return acronyms


# ── Item upload ────────────────────────────────────────────────────────────────

def upload_acronym(wbi: WikibaseIntegrator, acr: dict, acronym_class_qid: str) -> str | None:
    """Create a single Wikibase item for one acronym. Returns QID or None."""
    item = wbi.item.new()

    # Label = the acronym code
    item.labels.set(language="en", value=acr["code"])

    # Description = "Acronym for: <first description>"
    first_desc = acr["descriptions"][0]["text"] if acr["descriptions"] else ""
    if first_desc:
        item.descriptions.set(language="en", value=f"Acronym for: {first_desc}")

    claims = []

    # ── instance of (P1) → Acronym class, qualifier P19="IPCC AR6" ────────────
    qual_source = Qualifiers()
    qual_source.add(wbi_datatypes.String(prop_nr=PROP_SOURCE_VER, value=SOURCE_QUALIFIER))
    claims.append(
        wbi_datatypes.Item(
            prop_nr=PROP_INSTANCE_OF,
            value=acronym_class_qid,
            qualifiers=qual_source,
        )
    )

    # ── Part of (P3) → one statement per report ───────────────────────────────
    for report_code in acr["reports"]:
        qid = REPORT_QIDS.get(report_code)
        if qid:
            claims.append(wbi_datatypes.Item(prop_nr=PROP_PART_OF, value=qid))
        else:
            print(f"    [WARN] Unknown report code '{report_code}' for {acr['code']} — skipped")

    # ── Definition (P13) → one statement per description, each qualified ──────
    for desc in acr["descriptions"]:
        qual_def = Qualifiers()
        qual_def.add(wbi_datatypes.String(prop_nr=PROP_SOURCE_VER, value=SOURCE_QUALIFIER))
        claims.append(
            wbi_datatypes.MonolingualText(
                prop_nr=PROP_DEFINITION,
                text=desc["text"],
                language="en",
                qualifiers=qual_def,
            )
        )

    item.claims.add(claims)

    if DRY_RUN:
        return None

    result = item.write()
    return result.id


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Connecting to {WIKIBASE_URL} …")
    wbi = connect()
    print("Connected.\n")

    # ── Step 1: ensure "Acronym" class item exists ─────────────────────────────
    if not ACRONYM_ITEM_QID:
        print("ACRONYM_ITEM_QID not set — creating 'Acronym' class item …")
        qid = ensure_acronym_class(wbi)
        print(f"\n  Created 'Acronym' class item: {qid}")
        print("\nAdd the following to your .env file and re-run:")
        print(f"  ACRONYM_ITEM_QID={qid}")
        return

    acronym_class_qid = ACRONYM_ITEM_QID
    print(f"'Acronym' class item : {acronym_class_qid}")

    # ── Step 2: parse XML ──────────────────────────────────────────────────────
    print(f"Parsing {XML_PATH} …")
    acronyms = parse_xml(XML_PATH)
    print(f"Found {len(acronyms)} acronyms.")

    if OFFSET:
        acronyms = acronyms[OFFSET:]
        print(f"OFFSET: skipping first {OFFSET} acronyms (already imported)")

    if LIMIT:
        acronyms = acronyms[:LIMIT]
        print(f"LIMIT: processing first {LIMIT} acronyms")

    print()

    # ── Step 3: upload ─────────────────────────────────────────────────────────
    uploaded: list[dict] = []
    failed:   list[dict] = []
    total = len(acronyms)

    for i, acr in enumerate(acronyms, 1):
        try:
            qid = upload_acronym(wbi, acr, acronym_class_qid)
            label = "[DRY RUN]" if DRY_RUN else qid
            uploaded.append({
                "id":      acr["id"],
                "code":    acr["code"],
                "qid":     qid,
                "reports": acr["reports"],
            })
            print(f"[{i:>4}/{total}] +  {acr['code']:30s}  →  {label}")
        except Exception as exc:
            failed.append({"id": acr["id"], "code": acr["code"], "error": str(exc)})
            print(f"[{i:>4}/{total}] x  {acr['code']:30s}  ERROR: {exc}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Summary")
    print(f"  Uploaded : {len(uploaded)}")
    print(f"  Failed   : {len(failed)}")
    if failed:
        print("\nFailed:")
        for f in failed:
            print(f"  {f['id']}  {f['code']}  —  {f['error']}")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as fh:
        json.dump({"uploaded": uploaded, "failed": failed}, fh, indent=2, ensure_ascii=False)
    print(f"\nLog saved to {LOG_PATH}")


if __name__ == "__main__":
    main()
