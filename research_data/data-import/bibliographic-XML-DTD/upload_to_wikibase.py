#!/usr/bin/env python3
"""
upload_to_wikibase.py  —  Import IPCC AR6 Bibliographic References into Wikibase.

Workflow (two-run bootstrap pattern)
--------------------------------------
Run 1  — Bootstrap (no property/class QIDs set in .env):
  Creates the "Reference" class item and all required properties, prints their
  QIDs/PIDs, then exits.  Add the printed values to .env and re-run.

Run 2+ — Import:
  Reads outputs/references.xml and creates one Wikibase item per <reference>.
  Each item receives bibliographic statements and one "cited in chapter"
  statement per <citation>, with reference provenance (P17 + P18).

Wikibase data model
--------------------
  Reference item
    label (en)             : Citation_Key
    description (en)       : "IPCC AR6 bibliographic reference"
    P1  instance of        -> REFERENCE_CLASS_QID
    P_REF_ID               : ClimateKG_Ref_ID string  (e.g. REF0001)
    P_CITATION_KEY         : citation_key string
    P_AUTHORS              : authors string
    P_YEAR                 : year  (Time, year precision)
    P_TITLE                : title string
    P_PUBLICATION_TYPE     : publication_type string
    P_SOURCE               : source string  (if present)
    P_VOLUME               : volume string  (if present)
    P_ISSUE                : issue string   (if present)
    P_PAGES                : pages string   (if present)
    P_DOI                  : doi ExternalID (if present)
    P_URL                  : url url        (if present)
    P_CITED_IN_CHAPTER     : chapter_qid (WikibaseItem)
        [repeated per citation]
        reference P17 reference URL   : source_url
        reference P18 date accessed   : date_accessed

Environment variables (.env or shell)
--------------------------------------
  WIKIBASE_URL             (default: http://localhost:8080)
  MW_API_URL               (default: {WIKIBASE_URL}/api.php)
  SPARQL_URL               (default: http://localhost:9999/bigdata/sparql)
  WB_USER                  (default: admin)
  WB_PASSWORD              required
  REFERENCE_CLASS_QID      set after Run 1  (e.g. Q4000)
  P_REF_ID                 set after Run 1  (e.g. P29)
  P_CITATION_KEY           set after Run 1
  P_AUTHORS                set after Run 1
  P_YEAR                   set after Run 1
  P_TITLE                  set after Run 1
  P_PUBLICATION_TYPE       set after Run 1
  P_SOURCE                 set after Run 1
  P_VOLUME                 set after Run 1
  P_ISSUE                  set after Run 1
  P_PAGES                  set after Run 1
  P_DOI                    set after Run 1
  P_URL                    set after Run 1
  P_CITED_IN_CHAPTER       set after Run 1

Optional control variables
---------------------------
  DRY_RUN=true   print actions without writing to Wikibase
  LIMIT=N        process only the first N references
  OFFSET=N       skip the first N references

Usage
-----
  python upload_to_wikibase.py
  DRY_RUN=true python upload_to_wikibase.py
  LIMIT=5 python upload_to_wikibase.py
"""

import os
import sys
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── Optional .env loading ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _env = Path(__file__).resolve().parent
    while _env != _env.parent:
        if (_env / ".env").exists():
            load_dotenv(_env / ".env")
            break
        _env = _env.parent
except ImportError:
    pass

try:
    from wikibaseintegrator import WikibaseIntegrator, wbi_login
    from wikibaseintegrator.wbi_config import config as wbi_config
    from wikibaseintegrator import datatypes as wbi_dt
    from wikibaseintegrator.models import References, Reference
except ImportError:
    sys.exit(
        "wikibaseintegrator not found.\n"
        "Install with:  pip install wikibaseintegrator\n"
    )

# ── Configuration ──────────────────────────────────────────────────────────────
WIKIBASE_URL = os.getenv("WIKIBASE_URL", "http://localhost:8080")
MW_API_URL   = os.getenv("MW_API_URL",   f"{WIKIBASE_URL}/api.php")
SPARQL_URL   = os.getenv("SPARQL_URL",   "http://localhost:9999/bigdata/sparql")
WB_USER      = os.getenv("WB_USER",      "admin")
WB_PASSWORD  = os.getenv("WB_PASSWORD",  "")

# Class / property QIDs — set via .env after the bootstrap run.
REFERENCE_CLASS_QID  = os.getenv("REFERENCE_CLASS_QID",  "")
P_INSTANCE_OF        = "P1"
P_REF_ID             = os.getenv("P_REF_ID",             "")
P_CITATION_KEY       = os.getenv("P_CITATION_KEY",        "")
P_AUTHORS            = os.getenv("P_AUTHORS",             "")
P_YEAR               = os.getenv("P_YEAR",               "")
P_TITLE              = os.getenv("P_TITLE",              "")
P_PUBLICATION_TYPE   = os.getenv("P_PUBLICATION_TYPE",   "")
P_SOURCE             = os.getenv("P_SOURCE",             "")
P_VOLUME             = os.getenv("P_VOLUME",             "")
P_ISSUE              = os.getenv("P_ISSUE",              "")
P_PAGES              = os.getenv("P_PAGES",              "")
P_DOI                = os.getenv("P_DOI",                "")
P_URL_PROP           = os.getenv("P_URL",                "")
P_CITED_IN_CHAPTER   = os.getenv("P_CITED_IN_CHAPTER",   "")

# Existing reference properties (do not recreate)
# P17 = reference URL (url)  — provenance source URL
# P18 = date accessed (time) — provenance date accessed
P17_REFERENCE_URL = "P17"
P18_DATE_ACCESSED = "P18"

XML_PATH  = Path(__file__).parent / "outputs" / "references.xml"
LOG_PATH  = Path(__file__).parent / "outputs" / "upload_log.json"

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
OFFSET  = int(os.getenv("OFFSET", "0"))
LIMIT   = int(os.getenv("LIMIT",  "0"))

# ── Helpers ────────────────────────────────────────────────────────────────────

def connect() -> WikibaseIntegrator:
    wbi_config["mediawiki_api_url"] = MW_API_URL
    wbi_config["sparql_endpoint_url"] = SPARQL_URL
    wbi_config["wikibase_url"] = WIKIBASE_URL
    login = wbi_login.Clientlogin(user=WB_USER, password=WB_PASSWORD)
    return WikibaseIntegrator(login=login)


def _get(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def build_reference(source_url: str, date_accessed_str: str) -> Reference | None:
    """Build a Wikibase Reference with P17 (URL) and P18 (Time) snaks."""
    ref = Reference()
    if source_url:
        ref.add(wbi_dt.URL(value=source_url, prop_nr=P17_REFERENCE_URL))
    if date_accessed_str:
        try:
            dt = datetime.strptime(date_accessed_str, "%d %B %Y")
            wb_time = f"+{dt.strftime('%Y-%m-%d')}T00:00:00Z"
            ref.add(wbi_dt.Time(time=wb_time, prop_nr=P18_DATE_ACCESSED, precision=11))
        except ValueError:
            pass
    return ref if ref.snaks else None


# ── Bootstrap ──────────────────────────────────────────────────────────────────

def bootstrap(wbi: WikibaseIntegrator) -> None:
    """Create the Reference class item and all bibliographic properties."""
    print("\n=== Bootstrap mode ===")
    print("Creating Reference class item and properties...\n")

    # Create the Reference class item
    item = wbi.item.new()
    item.labels.set(language="en", value="Reference")
    item.descriptions.set(language="en", value="A bibliographic reference cited in IPCC AR6")
    if not DRY_RUN:
        item.write()
        print(f"REFERENCE_CLASS_QID={item.id}")
    else:
        print("DRY_RUN: would create Reference class item")

    # Property definitions: (label, description, datatype)
    properties = [
        ("ClimateKG Reference ID", "stable identifier for this reference",          "string"),
        ("citation key",           "short citation key (e.g. Smith2021)",            "string"),
        ("authors",                "semicolon-separated list of authors",            "string"),
        ("year",                   "publication year",                               "time"),
        ("title",                  "full title of the work",                         "string"),
        ("publication type",       "type of publication (article, book, etc.)",      "string"),
        ("source",                 "journal name, book title, or publisher",         "string"),
        ("volume",                 "volume number",                                  "string"),
        ("issue",                  "issue number",                                   "string"),
        ("pages",                  "page range",                                     "string"),
        ("DOI",                    "Digital Object Identifier (bare, no prefix)",    "external-id"),
        ("URL",                    "URL of the resource",                            "url"),
        ("cited in chapter",       "IPCC AR6 chapter that cites this reference",     "wikibase-item"),
    ]

    env_vars = [
        "P_REF_ID", "P_CITATION_KEY", "P_AUTHORS", "P_YEAR", "P_TITLE",
        "P_PUBLICATION_TYPE", "P_SOURCE", "P_VOLUME", "P_ISSUE", "P_PAGES",
        "P_DOI", "P_URL", "P_CITED_IN_CHAPTER",
    ]

    print("\nAdd these to C:\\Wikibase\\.env after bootstrap:\n")
    for (label, description, datatype), env_var in zip(properties, env_vars):
        if DRY_RUN:
            print(f"DRY_RUN: would create property '{label}' ({datatype}) -> {env_var}=P???")
            continue
        prop = wbi.property.new()
        prop.labels.set(language="en", value=label)
        prop.descriptions.set(language="en", value=description)
        prop.datatype = datatype
        prop.write()
        print(f"{env_var}={prop.id}   # {label}")

    print("\nBootstrap complete. Add the values above to .env, then re-run.")
    sys.exit(0)


# ── Import ─────────────────────────────────────────────────────────────────────

def import_references(wbi: WikibaseIntegrator) -> None:
    """Parse references.xml and create one Wikibase item per <reference>."""
    if not XML_PATH.exists():
        sys.exit(f"XML not found: {XML_PATH}\nRun csv_to_xml.py first.")

    tree = ET.parse(XML_PATH)
    all_refs = tree.getroot().findall("reference")

    # Apply OFFSET and LIMIT
    refs = all_refs[OFFSET:]
    if LIMIT:
        refs = refs[:LIMIT]

    total = len(refs)
    print(f"Parsed {len(all_refs)} references from {XML_PATH}")
    print(f"Processing {total} (offset={OFFSET}, limit={LIMIT or 'all'})\n")

    created = 0
    errors = 0
    log: list[dict] = []

    for idx, ref_el in enumerate(refs, start=1):
        ref_id     = ref_el.get("id", "")
        label      = _get(ref_el, "citation_key") or ref_id
        authors    = _get(ref_el, "authors")
        year_str   = _get(ref_el, "year")
        title      = _get(ref_el, "title")
        pub_type   = _get(ref_el, "publication_type")
        source     = _get(ref_el, "source")
        volume     = _get(ref_el, "volume")
        issue      = _get(ref_el, "issue")
        pages      = _get(ref_el, "pages")
        doi        = _get(ref_el, "doi")
        url        = _get(ref_el, "url")
        ck_ref_id  = _get(ref_el, "climatkg_ref_id")

        print(f"[{idx}/{total}] {label} ({ref_id}) ...", end=" ", flush=True)

        if DRY_RUN:
            print("DRY_RUN")
            log.append({"ref_id": ref_id, "label": label, "status": "dry_run"})
            continue

        try:
            item = wbi.item.new()
            item.labels.set(language="en", value=label)
            item.descriptions.set(language="en", value="IPCC AR6 bibliographic reference")

            data = [
                wbi_dt.Item(value=REFERENCE_CLASS_QID, prop_nr=P_INSTANCE_OF),
                wbi_dt.String(value=ck_ref_id,  prop_nr=P_REF_ID),
                wbi_dt.String(value=label,       prop_nr=P_CITATION_KEY),
                wbi_dt.String(value=authors,     prop_nr=P_AUTHORS),
                wbi_dt.String(value=title,       prop_nr=P_TITLE),
                wbi_dt.String(value=pub_type,    prop_nr=P_PUBLICATION_TYPE),
            ]

            # Year as Time (year precision = 9)
            if year_str:
                try:
                    data.append(wbi_dt.Time(
                        time=f"+{year_str}-01-01T00:00:00Z",
                        prop_nr=P_YEAR,
                        precision=9,
                    ))
                except Exception:
                    pass

            # Optional string fields
            for val, prop in [
                (source, P_SOURCE), (volume, P_VOLUME), (issue, P_ISSUE), (pages, P_PAGES),
            ]:
                if val and prop:
                    data.append(wbi_dt.String(value=val, prop_nr=prop))

            # DOI as ExternalID
            if doi and P_DOI:
                data.append(wbi_dt.ExternalID(value=doi, prop_nr=P_DOI))

            # URL
            if url and P_URL_PROP:
                data.append(wbi_dt.URL(value=url, prop_nr=P_URL_PROP))

            # Cited-in-chapter statements, one per <citation>
            for cit_el in ref_el.findall("citations/citation"):
                chapter_qid   = cit_el.get("chapter_qid", "")
                source_url    = _get(cit_el, "source_url")
                date_accessed = _get(cit_el, "date_accessed")

                if not chapter_qid or not P_CITED_IN_CHAPTER:
                    continue

                refs_obj = References()
                ref_prov = build_reference(source_url, date_accessed)
                if ref_prov:
                    refs_obj.add(ref_prov)

                data.append(wbi_dt.Item(
                    value=chapter_qid,
                    prop_nr=P_CITED_IN_CHAPTER,
                    references=refs_obj,
                ))

            item.claims.add(data)
            item.write()
            print(item.id)
            log.append({"ref_id": ref_id, "label": label, "qid": item.id, "status": "created"})
            created += 1

        except Exception as exc:
            print(f"ERROR: {exc}")
            log.append({"ref_id": ref_id, "label": label, "error": str(exc), "status": "error"})
            errors += 1

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone.  Created: {created}  Errors: {errors}")
    print(f"Log: {LOG_PATH}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    if not WB_PASSWORD:
        sys.exit("WB_PASSWORD is not set. Add it to C:\\Wikibase\\.env")

    wbi = connect()

    # Bootstrap mode: run if no class QID set yet
    if not REFERENCE_CLASS_QID:
        bootstrap(wbi)
    else:
        import_references(wbi)


if __name__ == "__main__":
    main()
