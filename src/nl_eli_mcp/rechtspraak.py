"""Dutch case law via Rechtspraak Open Data (data.rechtspraak.nl).

A separate source from the BWB SRU legislation API: the Council for the Judiciary publishes
all Dutch court decisions as open data, keyed by ECLI. Two endpoints (keyless):

- ``GET /uitspraken/zoeken`` -> an Atom feed of ECLIs (filtered by date / court / subject;
  the open-data search has **no free-text query** - discovery is by metadata).
- ``GET /uitspraken/content?id=ECLI:NL:...`` -> an ``open-rechtspraak`` XML document with RDF
  metadata (identifier/creator/date/zaaknummer/...) and the full ``<uitspraak>`` text.

Case law carries a native **ECLI**, not an ELI. Parsed with the stdlib ElementTree.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

import anyio
import httpx

from .cache import HttpCache

RECHTSPRAAK_BASE = "https://data.rechtspraak.nl/uitspraken"
DETAILS_BASE = "https://uitspraken.rechtspraak.nl/details"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "nl-eli-mcp/0.2.0 (+https://github.com/matematicsolutions/nl-eli-mcp)"

ATOM_NS = "http://www.w3.org/2005/Atom"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DCTERMS_NS = "http://purl.org/dc/terms/"
PSI_NS = "http://psi.rechtspraak.nl/"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class RechtspraakError(Exception):
    """Raised when a Rechtspraak Open Data response cannot be retrieved."""


class RechtspraakClient:
    """Async client for Rechtspraak Open Data. Use as ``async with RechtspraakClient() as c:``."""

    def __init__(
        self,
        base_url: str = RECHTSPRAAK_BASE,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/xml"},
            follow_redirects=True,
        )

    async def __aenter__(self) -> RechtspraakClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get(self, url: str, *, category: str) -> str:
        cached = self._cache.get(url)
        if cached is not None and isinstance(cached, str):
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url)
                resp.raise_for_status()
                self._cache.set(url, resp.text, ttl=HttpCache.ttl_for(category))
                return resp.text
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def search(self, params: list[tuple[str, str]]) -> str:
        from urllib.parse import urlencode

        url = f"{self.base_url}/zoeken?{urlencode(params)}"
        return await self._get(url, category="search")

    async def get_decision(self, ecli: str) -> str:
        url = f"{self.base_url}/content?id={quote(ecli)}"
        return await self._get(url, category="act")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _strip_preamble(xml_text: str) -> str:
    """Drop any BOM / whitespace before the XML declaration (Rechtspraak emits a BOM)."""
    idx = xml_text.find("<?xml")
    if idx == -1:
        idx = xml_text.find("<")
    return xml_text[idx:] if idx > 0 else xml_text


def _atom(tag: str) -> str:
    return f"{{{ATOM_NS}}}{tag}"


def parse_search_feed(atom_xml: str) -> dict[str, Any]:
    """Parse the Atom feed from /zoeken into {total, hits:[{ecli,title,source_url}]}."""
    try:
        root = ET.fromstring(_strip_preamble(atom_xml))
    except ET.ParseError as exc:
        raise RechtspraakError(f"malformed Atom feed: {exc}") from exc

    total: int | None = None
    subtitle = root.find(_atom("subtitle"))
    if subtitle is not None and subtitle.text:
        digits = "".join(c for c in subtitle.text if c.isdigit())
        if digits:
            total = int(digits)

    hits: list[dict[str, Any]] = []
    for entry in root.findall(_atom("entry")):
        ecli_el = entry.find(_atom("id"))
        title_el = entry.find(_atom("title"))
        ecli = ecli_el.text.strip() if ecli_el is not None and ecli_el.text else None
        title = title_el.text.strip() if title_el is not None and title_el.text else None
        html_url = None
        for link in entry.findall(_atom("link")):
            if link.get("rel") == "alternate" and link.get("href"):
                html_url = link.get("href")
                break
        if ecli:
            hits.append(
                {
                    "ecli": ecli,
                    "title": title,
                    "human_readable_citation": title,
                    "source_url": html_url or f"{DETAILS_BASE}?id={ecli}",
                }
            )
    return {"total": total if total is not None else len(hits), "hits": hits}


def _dcterms(root: ET.Element, name: str) -> str | None:
    el = root.find(f".//{{{DCTERMS_NS}}}{name}")
    if el is not None and el.text and el.text.strip():
        return el.text.strip()
    return None


def parse_decision(doc_xml: str) -> dict[str, Any] | None:
    """Parse an open-rechtspraak content document into metadata + full text."""
    try:
        root = ET.fromstring(_strip_preamble(doc_xml))
    except ET.ParseError:
        return None

    ecli = _dcterms(root, "identifier")
    if not ecli:
        return None
    court = _dcterms(root, "creator")
    date = _dcterms(root, "date")
    issued = _dcterms(root, "issued")
    subject = _dcterms(root, "subject")
    title = _dcterms(root, "title")
    zaaknummer = None
    zn = root.find(f".//{{{PSI_NS}}}zaaknummer")
    if zn is not None and zn.text and zn.text.strip():
        zaaknummer = zn.text.strip()

    # Full text: concatenate the <uitspraak> (or <conclusie>) element's text content.
    body = None
    for local in ("uitspraak", "conclusie"):
        node = next((e for e in root.iter() if e.tag.endswith("}" + local)), None)
        if node is not None:
            text = " ".join(t.strip() for t in node.itertext() if t and t.strip())
            if text:
                body = text
                break

    citation = title
    if not citation:
        parts = [p for p in (court, date, zaaknummer) if p]
        citation = ", ".join(parts) if parts else ecli

    return {
        "ecli": ecli,
        "court": court,
        "date": date,
        "issued": issued,
        "subject": subject,
        "zaaknummer": zaaknummer,
        "title": title,
        "text": body,
        "human_readable_citation": citation,
        "source_url": f"{DETAILS_BASE}?id={ecli}",
    }
