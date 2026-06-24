"""Offline parser tests against committed KOOP BWB SRU fixtures."""

from __future__ import annotations

from pathlib import Path

from nl_eli_mcp.citations import (
    _browsable_url,
    dedupe_by_bwb_id,
    number_of_records,
    parse_records,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_single_act_citation_contract():
    xml = _load("get_act_BWBR0005537.xml")
    records = parse_records(xml)
    assert records, "expected at least one gzd record"
    rec = records[0]
    assert rec["bwb_id"] == "BWBR0005537"
    assert rec["title"] == "Algemene wet bestuursrecht"
    assert rec["human_readable_citation"] == "Algemene wet bestuursrecht"
    # eli_uri = the official persistent toestand identifier (NL has no native /eli/).
    assert rec["eli_uri"].startswith("http://wetten.overheid.nl/id/BWBR0005537/")
    assert "/eli/" not in rec["eli_uri"]
    assert rec["source_url"].startswith("https://wetten.overheid.nl/BWBR0005537/")
    assert rec["version_date"]
    assert rec["text_url"].startswith(
        "https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0005537/"
    )


def test_number_of_records():
    xml = _load("get_act_BWBR0005537.xml")
    assert number_of_records(xml) == 1


def test_search_returns_distinct_acts():
    xml = _load("search_bestuursrecht.xml")
    records = parse_records(xml)
    assert len(records) >= 2
    distinct = dedupe_by_bwb_id(records)
    ids = [r["bwb_id"] for r in distinct]
    assert len(ids) == len(set(ids)), "dedupe must yield unique bwb_id"
    for rec in distinct:
        assert rec["bwb_id"].startswith("BWBR")
        assert rec["human_readable_citation"]
        assert rec["eli_uri"]
        assert rec["source_url"]


def test_browsable_url_derivation():
    toestand = "http://wetten.overheid.nl/id/BWBR0005537/2026-06-04/0"
    assert _browsable_url(toestand) == "https://wetten.overheid.nl/BWBR0005537/2026-06-04"
    assert _browsable_url(None) is None
    assert _browsable_url("not-a-toestand") is None


def test_parse_garbage_is_empty():
    assert parse_records("<not-sru/>") == []
    assert parse_records("totally not xml <<<") == []
