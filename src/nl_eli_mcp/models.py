"""Pydantic v2 models for the Dutch BWB (KOOP SRU) API + nl-eli-mcp."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

DATASET_NOTE = (
    "BWB (Basiswettenbestand) is the official consolidated body of Dutch national "
    "legislation, served by KOOP over SRU. Each act is identified by a BWB id (e.g. "
    "BWBR0005537) and has many time-stamped versions (toestanden); tools default to the "
    "version in force on a given date (today unless on_date is set). The Netherlands does "
    "NOT publish native ELI (/eli/) URIs on consolidated BWB - eli_uri carries the official "
    "persistent identifier (the wetten.overheid.nl/id toestand URI). This MVP covers "
    "consolidated legislation; case law is exposed separately via the Rechtspraak tools."
)

CASE_DATASET_NOTE = (
    "Dutch case law via Rechtspraak Open Data (data.rechtspraak.nl), keyed by native ECLI. "
    "The open-data search has NO free-text query - discover decisions by date range (and "
    "optional court/subject), then fetch a decision by its ECLI. Decisions carry an 'ecli' "
    "(not an ELI)."
)


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class BwbAct(_Tolerant):
    """A Dutch consolidated act (one toestand / version), parsed from a KOOP SRU gzd record."""

    bwb_id: str | None = None
    title: str | None = None
    act_type: str | None = None
    authority: str | None = None
    version_date: str | None = None
    date_modified: str | None = None
    legal_areas: list[str] = Field(default_factory=list)

    # Citation contract (Art. 4 CONSTITUTION).
    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None

    # Internal: fetchable consolidated XML location (used by nl_get_text).
    text_url: str | None = None


class SearchResult(_Tolerant):
    """Result of ``nl_search`` - distinct acts in force, one entry per BWB id."""

    query: str
    on_date: str
    total_matched: int
    returned: int
    items: list[BwbAct] = Field(default_factory=list)
    dataset_note: str = DATASET_NOTE


class CaseHit(_Tolerant):
    """One Rechtspraak search hit (an ECLI)."""

    ecli: str | None = None
    title: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class CaseSearchResult(_Tolerant):
    """Result of ``nl_case_search`` - decisions matching the metadata filters."""

    total: int
    returned: int
    items: list[CaseHit] = Field(default_factory=list)
    dataset_note: str = CASE_DATASET_NOTE


class Decision(_Tolerant):
    """Result of ``nl_get_decision`` - a Dutch court decision with native ECLI."""

    ecli: str | None = None
    court: str | None = None
    date: str | None = None
    issued: str | None = None
    subject: str | None = None
    zaaknummer: str | None = None
    title: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None
    text: str | None = None
    byte_size: int | None = None
    dataset_note: str = CASE_DATASET_NOTE


class LawText(_Tolerant):
    """Result of ``nl_get_text`` (full consolidated XML of one version)."""

    bwb_id: str
    on_date: str
    version_date: str | None = None
    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None
    text_url: str | None = None
    format: str = "bwb-toestand-xml"
    content: str | None = None
    byte_size: int | None = None
    dataset_note: str = DATASET_NOTE
