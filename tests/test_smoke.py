"""Live smoke tests against the KOOP BWB SRU API.

These hit the network (zoekservice.overheid.nl + the official repository host). They are
skipped automatically if the host is unreachable. Run explicitly with:

    pytest tests/test_smoke.py
"""

from __future__ import annotations

import httpx
import pytest

from nl_eli_mcp.server import nl_get_act, nl_get_text, nl_search

AWB = "BWBR0005537"  # Algemene wet bestuursrecht


def _live_or_skip() -> None:
    try:
        r = httpx.get(
            "https://zoekservice.overheid.nl/sru/Search",
            params={
                "x-connection": "BWB",
                "operation": "searchRetrieve",
                "version": "1.2",
                "query": "dcterms.identifier=BWBR0005537",
                "maximumRecords": "1",
            },
            timeout=20.0,
        )
        r.raise_for_status()
    except Exception as exc:  # pragma: no cover - network gate
        pytest.skip(f"KOOP BWB SRU not reachable: {exc}")


@pytest.mark.asyncio
async def test_smoke_search():
    _live_or_skip()
    result = await nl_search("bestuursrecht")
    assert result.returned >= 1
    ids = [a.bwb_id for a in result.items]
    assert len(ids) == len(set(ids)), "search items must be distinct acts"
    for act in result.items:
        assert act.eli_uri and act.human_readable_citation and act.source_url


@pytest.mark.asyncio
async def test_smoke_get_act():
    _live_or_skip()
    act = await nl_get_act(AWB)
    assert act.bwb_id == AWB
    assert act.title == "Algemene wet bestuursrecht"
    assert act.eli_uri.startswith("http://wetten.overheid.nl/id/BWBR0005537/")
    assert "/eli/" not in act.eli_uri
    assert act.source_url.startswith("https://wetten.overheid.nl/BWBR0005537/")


@pytest.mark.asyncio
async def test_smoke_get_text():
    _live_or_skip()
    text = await nl_get_text(AWB)
    assert text.bwb_id == AWB
    assert text.content and text.byte_size and text.byte_size > 10_000
    assert "<toestand" in text.content[:2000]
    assert text.eli_uri and text.human_readable_citation and text.source_url
