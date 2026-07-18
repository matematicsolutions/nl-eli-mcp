"""FastMCP entry point - Dutch consolidated legislation (BWB) tools.

Run:

    python -m nl_eli_mcp.server

Configuration via env:

- ``NL_ELI_CACHE_DIR`` (default ``~/.matematic/cache/nl-eli``)
- ``NL_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``NL_ELI_BASE_URL`` (default ``https://zoekservice.overheid.nl/sru/Search``)
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .audit import AuditLogger, hash_input, timer
from .citations import dedupe_by_bwb_id, number_of_records, parse_records
from . import runtime
from .client import DEFAULT_BASE_URL, KoopBwbClient, NlError
from .models import (
    BwbAct,
    CaseHit,
    CaseSearchResult,
    Decision,
    LawText,
    SearchResult,
)
from .rechtspraak import (
    RechtspraakClient,
    RechtspraakError,
    parse_decision,
    parse_search_feed,
)

INSTRUCTIONS = """\
This MCP server exposes the official Dutch consolidated legislation BWB (Basiswettenbestand) through the KOOP SRU API (zoekservice.overheid.nl, keyless). It serves consolidated national acts as XML. Every response carries a stable `eli_uri`, a `human_readable_citation` and a `source_url` (the citation contract).

## Versions and "in force on a date"

Each BWB act (e.g. `BWBR0005537`) has many time-stamped versions (toestanden). The tools default to the version **in force today**; pass `on_date` (YYYY-MM-DD) to pin a historical or future version. An act with no version valid on that date returns `not_found` - retry with another `on_date`.

This server also exposes Dutch **case law** via Rechtspraak Open Data (data.rechtspraak.nl), keyed by native ECLI - a separate source from BWB legislation.

## Call order

1. `nl_search` - find acts by words in the title that are in force on `on_date`. Returns distinct acts, each with `bwb_id`, `eli_uri`, `human_readable_citation`, `source_url`.
2. `nl_get_act` - metadata for one act by `bwb_id`: `eli_uri`, title, authority, version_date.
3. `nl_get_text` - the full consolidated XML of one act by `bwb_id`.
4. `nl_case_search` - list court decisions (Rechtspraak) by `date_from` / `date_to` (and optional `creator` / `subject` URIs). The open-data search has NO free-text query. Each hit carries a native `ecli`.
5. `nl_get_decision` - a decision by its `ecli` (e.g. `ECLI:NL:HR:2020:1`): court, dates, zaaknummer and the full text.

## Hard constraints

- **eli_uri is the citability key, but the Netherlands does NOT publish native ELI (/eli/) URIs on consolidated BWB.** `eli_uri` therefore carries the official persistent identifier - the `wetten.overheid.nl/id` toestand URI (e.g. `http://wetten.overheid.nl/id/BWBR0005537/2026-06-04/0`). Never fabricate a `/eli/` URI.
- **Case law carries a native `ecli`, not an ELI** - cite it verbatim; never invent one.
- **Legislation search is title-based; case-law search is metadata-based (no free text)** - `nl_search` matches words in the act title; `nl_case_search` filters by date / court / subject.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user.
- **No modification of official text** - returned verbatim from KOOP / Rechtspraak.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/nl-eli-mcp.jsonl`.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or malformed (e.g. a bad `bwb_id`, `ecli` or `on_date`).
- `not_found` - no act / no version in force on `on_date`, or no decision for that `ecli`.
- `upstream_error` - a KOOP / Rechtspraak API error (HTTP, timeout, malformed XML). Retry once before surfacing.

## Response style

- Cite acts as `human_readable_citation` with the identifier: "Algemene wet bestuursrecht, http://wetten.overheid.nl/id/BWBR0005537/2026-06-04/0".
- Cite decisions with their `ecli` and `source_url`.
- NEVER invent a `bwb_id`, an `ecli`, a title or an identifier - take each from the tool output.
"""

_BWB_ID_RE = re.compile(r"^BWBR\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_SEARCH_RECORDS = 50


class ToolError(Exception):
    """Structured error for nl-eli MCP tools - visible to the LLM with a [code] prefix."""

    VALID_CODES = frozenset({"invalid_arg", "not_found", "upstream_error"})

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown ToolError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,
)

mcp: FastMCP = FastMCP(name="nl-eli-mcp", instructions=INSTRUCTIONS)


def _base_url() -> str:
    return os.environ.get("NL_ELI_BASE_URL", runtime.base_url("eli", DEFAULT_BASE_URL)).rstrip("/")


def _audit() -> AuditLogger:
    return AuditLogger()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _map_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No record found in the KOOP BWB repository.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"KOOP API error: {type(exc).__name__}: {exc}")
    if isinstance(exc, (NlError, RechtspraakError)):
        return ToolError("upstream_error", str(exc))
    return exc


def _resolve_date(on_date: str | None) -> str:
    if on_date is None:
        return _today()
    if not _DATE_RE.match(on_date):
        raise ToolError("invalid_arg", f"on_date={on_date!r} must be YYYY-MM-DD.")
    return on_date


def _check_bwb_id(bwb_id: str) -> str:
    cleaned = bwb_id.strip()
    if not _BWB_ID_RE.match(cleaned):
        raise ToolError("invalid_arg", f"bwb_id={bwb_id!r} must look like 'BWBR0005537'.")
    return cleaned


# ---------------------------------------------------------------------------
# nl_search
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def nl_search(query: str, on_date: str | None = None) -> SearchResult:
    """Search Dutch consolidated acts by words in the title, in force on a date.

    Args:
        query: words to match in the act title, e.g. ``"bestuursrecht"``.
        on_date: optional ``YYYY-MM-DD``; defaults to today (acts in force today).

    Returns:
        ``SearchResult`` with distinct ``items: list[BwbAct]``, each carrying the citation contract.
    """
    audit = _audit()
    if not query or not query.strip():
        raise ToolError("invalid_arg", "query must be a non-empty string.")
    date = _resolve_date(on_date)
    input_hash = hash_input({"query": query, "on_date": date})

    with timer() as t:
        try:
            async with KoopBwbClient(base_url=_base_url()) as client:
                xml = await client.search_by_title(query, date, maximum_records=_MAX_SEARCH_RECORDS)
        except Exception as exc:
            audit.log(tool="nl_search", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    total = number_of_records(xml)
    records = dedupe_by_bwb_id(parse_records(xml))
    items = [BwbAct.model_validate(r) for r in records]
    result = SearchResult(
        query=query, on_date=date, total_matched=total, returned=len(items), items=items
    )
    audit.log(tool="nl_search", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# nl_get_act
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def nl_get_act(bwb_id: str, on_date: str | None = None) -> BwbAct:
    """Fetch metadata for the version of a Dutch act in force on a date.

    Args:
        bwb_id: e.g. ``"BWBR0005537"``.
        on_date: optional ``YYYY-MM-DD``; defaults to today.

    Returns:
        ``BwbAct`` with ``eli_uri``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    cleaned = _check_bwb_id(bwb_id)
    date = _resolve_date(on_date)
    input_hash = hash_input({"bwb_id": cleaned, "on_date": date})

    with timer() as t:
        try:
            async with KoopBwbClient(base_url=_base_url()) as client:
                xml = await client.get_version_record(cleaned, date)
        except Exception as exc:
            audit.log(tool="nl_get_act", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    records = parse_records(xml)
    if not records:
        raise ToolError("not_found", f"No version of {cleaned} in force on {date}.")
    act = BwbAct.model_validate(records[0])
    audit.log(tool="nl_get_act", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return act


# ---------------------------------------------------------------------------
# nl_get_text
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def nl_get_text(bwb_id: str, on_date: str | None = None) -> LawText:
    """Fetch the full consolidated XML of a Dutch act in force on a date.

    Args:
        bwb_id: e.g. ``"BWBR0005537"``.
        on_date: optional ``YYYY-MM-DD``; defaults to today.

    Returns:
        ``LawText`` with the citation contract and ``content`` (BWB toestand XML).
    """
    audit = _audit()
    cleaned = _check_bwb_id(bwb_id)
    date = _resolve_date(on_date)
    input_hash = hash_input({"bwb_id": cleaned, "on_date": date})

    with timer() as t:
        try:
            async with KoopBwbClient(base_url=_base_url()) as client:
                meta_xml = await client.get_version_record(cleaned, date)
                records = parse_records(meta_xml)
                if not records:
                    raise ToolError("not_found", f"No version of {cleaned} in force on {date}.")
                meta = records[0]
                text_url = meta.get("text_url")
                if not text_url:
                    raise ToolError("not_found", f"No text location for {cleaned} on {date}.")
                content = await client.fetch_text(text_url)
        except ToolError:
            audit.log(tool="nl_get_text", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error="not_found")
            raise
        except Exception as exc:
            audit.log(tool="nl_get_text", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    result = LawText(
        bwb_id=cleaned,
        on_date=date,
        version_date=meta.get("version_date"),
        eli_uri=meta.get("eli_uri"),
        human_readable_citation=meta.get("human_readable_citation"),
        source_url=meta.get("source_url"),
        text_url=text_url,
        content=content,
        byte_size=len(content.encode("utf-8")),
    )
    audit.log(tool="nl_get_text", input_hash=input_hash, output_count_or_size=result.byte_size or 0,
              duration_ms=t.duration_ms, status="ok")
    return result


_ECLI_RE = re.compile(r"^ECLI:[A-Z]{2}:[A-Za-z0-9.]+:\d{4}:[A-Za-z0-9.]+$")
_MAX_CASE_RECORDS = 50


# ---------------------------------------------------------------------------
# nl_case_search (Rechtspraak)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def nl_case_search(
    date_from: str | None = None,
    date_to: str | None = None,
    creator: str | None = None,
    subject: str | None = None,
    max_results: int = 10,
) -> CaseSearchResult:
    """List Dutch court decisions (Rechtspraak Open Data) by metadata filters.

    The open-data search has NO free-text query. Filter by a date range and, optionally, a
    court (`creator`) or legal-area (`subject`) authority URI, then fetch a decision with
    ``nl_get_decision``.

    Args:
        date_from: earliest decision date (YYYY-MM-DD).
        date_to: latest decision date (YYYY-MM-DD).
        creator: optional court authority URI (Instantie), passed through verbatim.
        subject: optional legal-area authority URI (Rechtsgebied), passed through verbatim.
        max_results: 1..50.

    Returns:
        ``CaseSearchResult`` with ``items: list[CaseHit]``, each carrying a native ``ecli``.
    """
    audit = _audit()
    for label, value in (("date_from", date_from), ("date_to", date_to)):
        if value is not None and not _DATE_RE.match(value):
            raise ToolError("invalid_arg", f"{label}={value!r} must be YYYY-MM-DD.")
    if not 1 <= max_results <= _MAX_CASE_RECORDS:
        raise ToolError("invalid_arg", f"max_results must be 1..{_MAX_CASE_RECORDS}.")

    params: list[tuple[str, str]] = [("type", "uitspraak"), ("max", str(max_results))]
    if date_from:
        params.append(("date", date_from))
    if date_to:
        params.append(("date", date_to))
    if creator:
        params.append(("creator", creator))
    if subject:
        params.append(("subject", subject))
    input_hash = hash_input(dict(params))

    with timer() as t:
        try:
            async with RechtspraakClient() as client:
                feed = await client.search(params)
        except Exception as exc:
            audit.log(tool="nl_case_search", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    parsed = parse_search_feed(feed)
    items = [CaseHit.model_validate(h) for h in parsed["hits"]]
    result = CaseSearchResult(total=parsed["total"], returned=len(items), items=items)
    audit.log(tool="nl_case_search", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
    return result


# ---------------------------------------------------------------------------
# nl_get_decision (Rechtspraak)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def nl_get_decision(ecli: str) -> Decision:
    """Fetch a Dutch court decision by its ECLI (Rechtspraak Open Data).

    Args:
        ecli: e.g. ``ECLI:NL:HR:2020:1``.

    Returns:
        ``Decision`` with the native ``ecli``, court, dates, zaaknummer, citation and full text.
    """
    audit = _audit()
    cleaned = (ecli or "").strip()
    if not _ECLI_RE.match(cleaned):
        raise ToolError("invalid_arg", f"ecli={ecli!r} must look like 'ECLI:NL:HR:2020:1'.")
    input_hash = hash_input({"ecli": cleaned})

    with timer() as t:
        try:
            async with RechtspraakClient() as client:
                doc = await client.get_decision(cleaned)
        except Exception as exc:
            audit.log(tool="nl_get_decision", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    parsed = parse_decision(doc)
    if parsed is None or not parsed.get("ecli"):
        raise ToolError("not_found", f"No decision found for {cleaned}.")
    text = parsed.get("text") or ""
    parsed["byte_size"] = len(text.encode("utf-8"))
    result = Decision.model_validate(parsed)
    audit.log(tool="nl_get_decision", input_hash=input_hash, output_count_or_size=result.byte_size or 0,
              duration_ms=t.duration_ms, status="ok")
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
