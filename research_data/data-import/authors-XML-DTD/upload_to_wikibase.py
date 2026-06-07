#!/usr/bin/env python3
"""
upload_to_wikibase.py  —  Import IPCC AR6 Authors into a Wikibase instance.

Workflow (two-run bootstrap pattern)
-------------------------------------
Run 1  — Bootstrap (no property/class QIDs set in .env):
  Creates the "Author" class item and all required properties, prints their
  QIDs/PIDs, then exits.  Add the printed values to .env and re-run.

Run 2+ — Import:
  Reads outputs/authors.xml and creates one Wikibase item per <author>.
  Each item receives biographical statements and one "contributed to chapter"
  statement per <contribution>, with Role as a qualifier.

Wikibase data model
--------------------
  Author item
    label (en)          : "First_Name Last_Name"
    description (en)    : "IPCC AR6 author"
    P1  instance of     → AUTHOR_CLASS_QID
    P_AUTHOR_ID         : ClimateKG_Author_ID string  (e.g. AU0001)
    P_LAST_NAME         : last_name string
    P_FIRST_NAME        : first_name string
    P_GENDER            : gender string  (F | M)
    P_CITIZENSHIP       : citizenship string
    P_COUNTRY_RESIDENCE : country_of_residence string
    P_AFFILIATION       : affiliation string
    P_CONTRIB_CHAPTER   : chapter_qid (WikibaseItem)
        qualifier P_ROLE: role string
        [repeated per chapter contribution]

Environment variables (.env or shell)
--------------------------------------
  WIKIBASE_URL         (default: http://localhost:8080)
  MW_API_URL           (default: {WIKIBASE_URL}/api.php)
  SPARQL_URL           (default: http://localhost:9999/bigdata/sparql)
  WB_USER              (default: admin)
  WB_PASSWORD          required
  AUTHOR_CLASS_QID     set after Run 1  (e.g. Q200)
  P_AUTHOR_ID          set after Run 1  (e.g. P20)
  P_LAST_NAME          set after Run 1
  P_FIRST_NAME         set after Run 1
  P_GENDER             set after Run 1
  P_CITIZENSHIP        set after Run 1
  P_COUNTRY_RESIDENCE  set after Run 1
  P_AFFILIATION        set after Run 1
  P_CONTRIB_CHAPTER    set after Run 1
  P_ROLE               set after Run 1

Optional control variables
---------------------------
  DRY_RUN=true   print actions without writing to Wikibase
  LIMIT=N        process only the first N authors
  OFFSET=N       skip the first N authors

Usage
-----
  python upload_to_wikibase.py           # bootstrap or full import
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
    from wikibaseintegrator.models import Qualifiers, References, Reference
except ImportError:
    sys.exit(
        "wikibaseintegrator not found.\n"
        "Install with:  pip install wikibaseintegrator\n"
    )

# ── Configuration ──────────────────────────────────────────────────────────────
WIKIBASE_URL = os.getenv("WIKIBASE_URL", "http://localhost:8080")
MW_API_URL   = os.getenv("MW_API_URL",   f"{WIKIBASE_URL}/w/api.php")
SPARQL_URL   = os.getenv("SPARQL_URL",   "http://localhost:9999/bigdata/sparql")
WB_USER      = os.getenv("WB_USER",      "admin")
WB_PASSWORD  = os.getenv("WB_PASSWORD",  "")

# Class / property QIDs — set via .env after the bootstrap run.
AUTHOR_CLASS_QID    = os.getenv("AUTHOR_CLASS_QID",    "")
P_INSTANCE_OF       = "P1"
P_AUTHOR_ID         = os.getenv("P_AUTHOR_ID",         "")
P_LAST_NAME         = os.getenv("P_LAST_NAME",         "")
P_FIRST_NAME        = os.getenv("P_FIRST_NAME",        "")
P_GENDER            = os.getenv("P_GENDER",            "")
P_CITIZENSHIP       = os.getenv("P_CITIZENSHIP",       "")
P_COUNTRY_RESIDENCE = os.getenv("P_COUNTRY_RESIDENCE", "")
P_AFFILIATION       = os.getenv("P_AFFILIATION",       "")
P_CONTRIB_CHAPTER   = os.getenv("P_CONTRIB_CHAPTER",   "")
P_ROLE              = os.getenv("P_ROLE",              "")

# Existing reference properties (do not recreate)
# P17 = reference URL (url)  — used as source URL reference on chapter contributions
# P18 = date accessed (time) — used as date accessed reference
P17_REFERENCE_URL = "P17"
P18_DATE_ACCESSED = "P18"

XML_PATH  = Path(__file__).parent / "outputs" / "authors.xml"
LOG_PATH  = Path(__file__).parent / "outputs" / "upload_log.json"

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
OFFSET  = int(os.getenv("OFFSET", "0"))
LIMIT   = int(os.getenv("LIMIT",  "0"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def connect() -> WikibaseIntegrator:
    wbi_config["MEDIAWIKI_API_URL"]   = MW_API_URL
    wbi_config["SPARQL_ENDPOINT_URL"] = SPARQL_URL
    wbi_config["WIKIBASE_URL"]        = WIKIBASE_URL
    login = wbi_login.Login(user=WB_USER, password=WB_PASSWORD)
    return WikibaseIntegrator(login=login)


def create_item(wbi: WikibaseIntegrator, label: str, description: str) -> str:
    """Create a bare item with label + description. Return QID."""
    item = wbi.item.new()
    item.labels.set(language="en", value=label)
    item.descriptions.set(language="en", value=description)
    if DRY_RUN:
        print(f"  [DRY RUN] Would create item: '{label}'")
        return "Q_DRY"
    result = item.write()
    return result.id


def create_property(wbi: WikibaseIntegrator, label: str, description: str,
                    datatype: str) -> str:
    """Create a property. Return PID."""
    prop = wbi.property.new(datatype=datatype)
    prop.labels.set(language="en", value=label)
    prop.descriptions.set(language="en", value=description)
    if DRY_RUN:
        print(f"  [DRY RUN] Would create property: '{label}' ({datatype})")
        return "P_DRY"
    result = prop.write()
    return result.id


# ── Bootstrap: create class + properties ──────────────────────────────────────

def bootstrap(wbi: WikibaseIntegrator) -> None:
    """
    Create the Author class item and all required properties.
    Print the resulting QIDs/PIDs for the user to add to .env.
    """
    print("=== Bootstrap: creating Author class item and properties ===\n")

    author_qid = create_item(wbi, "Author", "IPCC AR6 author (person)")
    print(f"AUTHOR_CLASS_QID={author_qid}")

    props = [
        ("ClimateKG Author ID",      "Stable ClimateKG identifier for an author (e.g. AU0001)",         "string",         "P_AUTHOR_ID"),
        ("last name",                "Family name of a person",                                          "string",         "P_LAST_NAME"),
        ("first name",               "Given name(s) of a person",                                        "string",         "P_FIRST_NAME"),
        ("gender",                   "Gender of a person (F or M)",                                      "string",         "P_GENDER"),
        ("citizenship",              "Country of citizenship",                                            "string",         "P_CITIZENSHIP"),
        ("country of residence",     "Country of residence during IPCC AR6",                             "string",         "P_COUNTRY_RESIDENCE"),
        ("affiliation",              "Institutional affiliation during IPCC AR6",                        "string",         "P_AFFILIATION"),
        ("contributed to chapter",   "IPCC AR6 chapter this person contributed to",                      "wikibase-item",  "P_CONTRIB_CHAPTER"),
        ("role",                     "Role of an author in a chapter contribution (qualifier)",           "string",         "P_ROLE"),
    ]

    for label, desc, datatype, env_key in props:
        pid = create_property(wbi, label, desc, datatype)
        print(f"{env_key}={pid}")

    print("\nAdd the values above to your .env file, then re-run to import authors.")


# ── XML parsing ────────────────────────────────────────────────────────────────

def parse_xml(xml_path: Path) -> list[dict]:
    """
    Parse outputs/authors.xml.
    Returns a list of author dicts, each with keys:
      id, climatkg_author_id, last_name, first_name, gender,
      citizenship, country_of_residence, affiliation,
      contributions: [{chapter_qid, report, chapter, role}, ...]
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    authors = []
    for a in root.findall("author"):
        def t(tag): return (a.findtext(tag) or "").strip()
        contribs = []
        for c in a.findall(".//contribution"):
            contribs.append({
                "chapter_qid": c.get("chapter_qid", ""),
                "report":      c.get("report", ""),
                "chapter":     c.get("chapter", ""),
                "role":        (c.findtext("role")         or "").strip(),
                "source_url":  (c.findtext("source_url")   or "").strip(),
                "date_accessed": (c.findtext("date_accessed") or "").strip(),
            })
        authors.append({
            "id":                   a.get("id"),
            "climatkg_author_id":   t("climatkg_author_id"),
            "last_name":            t("last_name"),
            "first_name":           t("first_name"),
            "gender":               t("gender"),
            "citizenship":          t("citizenship"),
            "country_of_residence": t("country_of_residence"),
            "affiliation":          t("affiliation"),
            "contributions":        contribs,
        })
    return authors


# ── Item upload ────────────────────────────────────────────────────────────────

def upload_author(wbi: WikibaseIntegrator, author: dict) -> str | None:
    """Create one Wikibase item for an author. Returns QID or None on error."""
    item = wbi.item.new()

    label = f"{author['first_name']} {author['last_name']}".strip()
    item.labels.set(language="en", value=label)
    item.descriptions.set(language="en", value="IPCC AR6 author")

    claims = []

    # instance of → Author class
    claims.append(wbi_dt.Item(value=AUTHOR_CLASS_QID, prop_nr=P_INSTANCE_OF))

    # Biographical string properties
    str_props = [
        (P_AUTHOR_ID,         author["climatkg_author_id"]),
        (P_LAST_NAME,         author["last_name"]),
        (P_FIRST_NAME,        author["first_name"]),
        (P_GENDER,            author["gender"]),
        (P_CITIZENSHIP,       author["citizenship"]),
        (P_COUNTRY_RESIDENCE, author["country_of_residence"]),
        (P_AFFILIATION,       author["affiliation"]),
    ]
    for prop, val in str_props:
        if prop and val:
            claims.append(wbi_dt.String(value=val, prop_nr=prop))

    # Chapter contributions (one statement per chapter, Role as qualifier,
    # source URL + date accessed as reference)
    for contrib in author["contributions"]:
        qid = contrib["chapter_qid"]
        role = contrib["role"]
        if not qid:
            continue
        qualifiers = Qualifiers()
        if P_ROLE and role:
            qualifiers.add(wbi_dt.String(value=role, prop_nr=P_ROLE))

        # Build reference: reference URL (P17) + date accessed (P18)
        refs = References()
        ref = Reference()
        if contrib.get("source_url"):
            ref.add(wbi_dt.URL(value=contrib["source_url"], prop_nr=P17_REFERENCE_URL))
        if contrib.get("date_accessed"):
            try:
                dt = datetime.strptime(contrib["date_accessed"], "%d %B %Y")
                wb_time = f"+{dt.strftime('%Y-%m-%d')}T00:00:00Z"
                ref.add(wbi_dt.Time(time=wb_time, prop_nr=P18_DATE_ACCESSED, precision=11))
            except ValueError:
                pass
        if ref.snaks:
            refs.add(ref)

        claims.append(
            wbi_dt.Item(
                value=qid,
                prop_nr=P_CONTRIB_CHAPTER,
                qualifiers=qualifiers,
                references=refs,
            )
        )

    item.claims.add(claims)

    if DRY_RUN:
        print(f"  [DRY RUN] Would create: {label}  ({author['id']})  "
              f"— {len(author['contributions'])} chapter(s)")
        return "Q_DRY"

    try:
        result = item.write()
        return result.id
    except Exception as exc:
        print(f"  ERROR uploading {label} ({author['id']}): {exc}")
        return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if not WB_PASSWORD:
        sys.exit("WB_PASSWORD is not set. Add it to .env or the environment.")

    wbi = connect()

    # Bootstrap mode: run if class QID not yet set
    if not AUTHOR_CLASS_QID:
        bootstrap(wbi)
        return

    # Import mode
    required = {
        "AUTHOR_CLASS_QID": AUTHOR_CLASS_QID,
        "P_AUTHOR_ID":      P_AUTHOR_ID,
        "P_LAST_NAME":      P_LAST_NAME,
        "P_FIRST_NAME":     P_FIRST_NAME,
        "P_CONTRIB_CHAPTER": P_CONTRIB_CHAPTER,
        "P_ROLE":           P_ROLE,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        sys.exit(f"Missing required env vars after bootstrap: {missing}")

    authors = parse_xml(XML_PATH)
    print(f"Parsed {len(authors)} authors from {XML_PATH}")

    # Apply offset / limit
    if OFFSET:
        authors = authors[OFFSET:]
    if LIMIT:
        authors = authors[:LIMIT]

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log: list[dict] = []
    ok = err = 0

    for i, author in enumerate(authors, 1):
        print(f"[{i}/{len(authors)}] {author['first_name']} {author['last_name']} "
              f"({author['id']}) ...", end=" ", flush=True)
        qid = upload_author(wbi, author)
        if qid:
            print(qid)
            log.append({"author_id": author["id"], "label": f"{author['first_name']} {author['last_name']}", "qid": qid})
            ok += 1
        else:
            log.append({"author_id": author["id"], "label": f"{author['first_name']} {author['last_name']}", "qid": None, "error": True})
            err += 1

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"\nDone.  Created: {ok}  Errors: {err}")
    print(f"Log: {LOG_PATH}")


if __name__ == "__main__":
    main()
