# nl-eli-mcp

An MCP server for the **Dutch consolidated legislation BWB** (Basiswettenbestand), served by
KOOP over the official SRU API (`zoekservice.overheid.nl`, keyless). It gives an AI agent the
version of an act **in force on a given date**, with a verifiable citation: a persistent
identifier, a human-readable citation, and a link to the official source.

Part of the **eu-legal-mcp** line by [MateMatic](https://matematic.co) — one connector per EU
member state, the same citation contract everywhere.

> **On ELI.** The Netherlands does **not** publish native ELI (`/eli/`) URIs on consolidated
> BWB. To keep the line's contract honest, `eli_uri` carries the official persistent
> identifier instead — the `wetten.overheid.nl/id` *toestand* URI
> (e.g. `http://wetten.overheid.nl/id/BWBR0005537/2026-06-04/0`). The connector never
> fabricates an `/eli/` URI and says so in its tool instructions. See `DISCOVERY.md`.

## Tools

| Tool | What it does |
|---|---|
| `nl_search(query, on_date=today)` | Find acts by words in the title that are in force on a date. Returns distinct acts, each with the citation contract. |
| `nl_get_act(bwb_id, on_date=today)` | Metadata for one act (e.g. `BWBR0005537`) — identifier, title, authority, version date. |
| `nl_get_text(bwb_id, on_date=today)` | The full consolidated XML (BWB *toestand*) of one act. |

Every response carries the **citation contract**:

- `eli_uri` — the official persistent identifier (toestand URI; see the ELI note above).
- `human_readable_citation` — the official short title (citeertitel), e.g. *Algemene wet bestuursrecht*.
- `source_url` — the browsable `wetten.overheid.nl` page for that version.

### Versions and dates

Each act has many time-stamped versions. The tools default to the version **in force today**;
pass `on_date` (`YYYY-MM-DD`) to pin a historical or future version. An act with no version
valid on that date returns `not_found` — retry with another `on_date`.

## Install

```bash
pip install -e ".[dev]"
```

Register it with your MCP client (see `.mcp.json.example`):

```json
{
  "mcpServers": {
    "nl-eli-mcp": {
      "command": "nl-eli-mcp",
      "env": {
        "NL_ELI_BASE_URL": "https://zoekservice.overheid.nl/sru/Search",
        "NL_ELI_CACHE_DIR": "~/.matematic/cache/nl-eli",
        "NL_ELI_AUDIT_DIR": "~/.matematic/audit"
      }
    }
  }
}
```

## Design

- **Public data only.** Read-only against the keyless KOOP SRU API and the official repository
  host; nothing is sent beyond the query / identifier and the date.
- **Audit log.** Every call appends one JSON line to `~/.matematic/audit/nl-eli-mcp.jsonl`
  (AI Act art. 12 record-keeping).
- **Vendor-neutral.** No LLM provider, no telemetry; own backoff + on-disk cache.
- **No fabrication.** Identifiers and titles are parsed from the source record. If KOOP's
  schema changes, the connector fails loudly rather than returning stale or invented data.

See `CONSTITUTION.md` (the 4 principles) and `DISCOVERY.md` (how the source was mapped).

## Tests

```bash
pytest tests/test_instructions_drift.py tests/test_parse.py   # offline
pytest tests/test_smoke.py                                     # live KOOP API
```

## Licence

Apache-2.0. The Dutch legislation served is official public data of the Kingdom of the
Netherlands; this connector adds no rights over it.
