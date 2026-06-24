"""Dutch BWB (KOOP SRU) record parsing + citation helpers.

KOOP serves consolidated Dutch legislation (BWB) over SRU 1.2. Each ``searchRetrieve``
response wraps one or more ``gzd`` records (namespace
``http://standaarden.overheid.nl/sru``). We parse with the stdlib ElementTree - no
third-party XML dependency.

Citation contract (Art. 4 CONSTITUTION):
- ``eli_uri``: the official persistent identifier of the version - the ``overheidbwb:toestand``
  URI ``http://wetten.overheid.nl/id/<bwb_id>/<date>/<n>``. The Netherlands does NOT publish
  native ELI (/eli/) URIs on consolidated BWB, so this field carries the equivalent stable
  identifier rather than a fabricated ELI.
- ``human_readable_citation``: the official short title (citeertitel), e.g.
  "Algemene wet bestuursrecht".
- ``source_url``: the browsable wetten.overheid.nl page for that version.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

NS = {
    "srw": "http://www.loc.gov/zing/srw/",
    "gzd": "http://standaarden.overheid.nl/sru",
    "dcterms": "http://purl.org/dc/terms/",
    "overheid": "http://standaarden.overheid.nl/owms/terms/",
    "overheidbwb": "http://standaarden.overheid.nl/bwb/terms/",
}

_TOESTAND_RE = re.compile(
    r"https?://wetten\.overheid\.nl/id/(BWBR\d+)/(\d{4}-\d{2}-\d{2})(?:/(\d+))?"
)


def _q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _browsable_url(toestand: str | None) -> str | None:
    """Derive the browsable wetten.overheid.nl page from a toestand id URI."""
    if not toestand:
        return None
    m = _TOESTAND_RE.search(toestand)
    if not m:
        return None
    bwb_id, date = m.group(1), m.group(2)
    return f"https://wetten.overheid.nl/{bwb_id}/{date}"


def _parse_gzd(gzd: ET.Element) -> dict[str, Any]:
    out: dict[str, Any] = {}

    bwb_id = _text(gzd.find(f".//{_q('dcterms', 'identifier')}"))
    title = _text(gzd.find(f".//{_q('dcterms', 'title')}"))
    act_type = _text(gzd.find(f".//{_q('dcterms', 'type')}"))
    authority = _text(gzd.find(f".//{_q('overheid', 'authority')}"))
    modified = _text(gzd.find(f".//{_q('dcterms', 'modified')}"))
    toestand = _text(gzd.find(f".//{_q('overheidbwb', 'toestand')}"))
    text_url = _text(gzd.find(f".//{_q('overheidbwb', 'locatie_toestand')}"))
    legal_areas = [
        t for t in (_text(e) for e in gzd.findall(f".//{_q('overheidbwb', 'rechtsgebied')}")) if t
    ]

    if bwb_id:
        out["bwb_id"] = bwb_id
    if title:
        out["title"] = title
    if act_type:
        out["act_type"] = act_type
    if authority:
        out["authority"] = authority
    if modified:
        out["date_modified"] = modified
    if legal_areas:
        out["legal_areas"] = legal_areas
    if text_url:
        out["text_url"] = text_url

    if toestand:
        out["eli_uri"] = toestand
        m = _TOESTAND_RE.search(toestand)
        if m:
            out["version_date"] = m.group(2)
        out["source_url"] = _browsable_url(toestand)

    # Citation = the official short title (citeertitel). NL cites laws by title.
    if title:
        out["human_readable_citation"] = title

    return out


def number_of_records(xml_text: str) -> int:
    """Total hits reported by the SRU response (independent of maximumRecords)."""
    m = re.search(r"<(?:\w+:)?numberOfRecords>(\d+)</", xml_text)
    return int(m.group(1)) if m else 0


def parse_records(xml_text: str) -> list[dict[str, Any]]:
    """Parse all gzd records from a KOOP SRU searchRetrieve response."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    records = root.findall(f".//{_q('gzd', 'gzd')}")
    return [_parse_gzd(g) for g in records]


def dedupe_by_bwb_id(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first record per BWB id (a query can still return >1 version per act)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in records:
        bwb_id = r.get("bwb_id")
        if not bwb_id or bwb_id in seen:
            continue
        seen.add(bwb_id)
        out.append(r)
    return out
