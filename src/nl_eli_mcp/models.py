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
    "consolidated legislation; case law (rechtspraak/ECLI) is not covered here."
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
