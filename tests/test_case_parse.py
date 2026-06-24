"""Offline parse tests for the Rechtspraak case-law source (no network)."""

from __future__ import annotations

from pathlib import Path

from nl_eli_mcp.rechtspraak import parse_decision, parse_search_feed

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_search_feed():
    atom = (FIXTURES / "rechtspraak_search.xml").read_text(encoding="utf-8")
    out = parse_search_feed(atom)
    assert out["total"] > 1000, "feed reports a large total of ECLIs"
    assert out["hits"], "expected entries"
    hit = out["hits"][0]
    assert hit["ecli"].startswith("ECLI:NL:")
    assert hit["human_readable_citation"]
    assert hit["source_url"].startswith("https://")


def test_parse_decision_native_ecli_and_text():
    doc = (FIXTURES / "rechtspraak_decision.xml").read_text(encoding="utf-8")
    rec = parse_decision(doc)
    assert rec is not None
    assert rec["ecli"] == "ECLI:NL:HR:2020:1"
    assert rec["court"] == "Hoge Raad"
    assert rec["date"]
    assert rec["zaaknummer"]
    assert rec["human_readable_citation"]
    assert rec["source_url"].endswith("id=ECLI:NL:HR:2020:1")
    assert rec["text"] and len(rec["text"]) > 100, "expected uitspraak body text"


def test_decision_is_ecli_not_eli():
    doc = (FIXTURES / "rechtspraak_decision.xml").read_text(encoding="utf-8")
    rec = parse_decision(doc)
    assert rec is not None
    # Case law carries ECLI, never an ELI.
    assert "eli_uri" not in rec
    assert "/eli/" not in (rec.get("source_url") or "")
