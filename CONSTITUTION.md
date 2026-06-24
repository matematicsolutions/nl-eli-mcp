# Constitution of nl-eli-mcp

Version: 0.1.0
Date: 2026-06-24
Licence: Apache-2.0

`nl-eli-mcp` is an MCP server for the Dutch consolidated legislation BWB
(Basiswettenbestand), served by KOOP over the SRU API (`zoekservice.overheid.nl`). It fetches
the version of an act in force on a given date, with a verifiable citation. The MVP covers
consolidated legislation; case law (rechtspraak / ECLI) is a later feature.

The 4 principles below are inherited from the `eu-legal-mcp` line Constitution (Article IV).

---

## Art. 1. Public data only

The KOOP SRU service over the BWB collection is the official, public source of Dutch
consolidated legislation (keyless Open Government Data). The server is read-only and sends
nothing beyond the search terms / identifier and the requested date.

## Art. 2. Mandatory audit log

Every tool call MUST append one JSON line to `~/.matematic/audit/nl-eli-mcp.jsonl`
(ts / tool / input_hash SHA-256 / output_count_or_size / duration_ms / status). Inability to
write = the tool returns an error, it does not silently skip.

## Art. 3. Vendor neutrality

No tool hardcodes an LLM provider, assumes a model, or adds commercial telemetry. The server
talks only to `zoekservice.overheid.nl` and the official repository host
`repository.officiele-overheidspublicaties.nl`, plus the local filesystem. Authentication:
none; own backoff + cache.

## Art. 4. A persistent identifier and a human-readable citation are mandatory

Every response MUST carry three fields:
- `eli_uri`: the official persistent identifier of the version. **The Netherlands does not
  publish native ELI (`/eli/`) URIs on consolidated BWB**, so this field carries the
  equivalent stable identifier - the `wetten.overheid.nl/id` toestand URI
  (e.g. `http://wetten.overheid.nl/id/BWBR0005537/2026-06-04/0`). It is parsed from the
  source record, never fabricated.
- `human_readable_citation`: the official short title (citeertitel),
  e.g. "Algemene wet bestuursrecht".
- `source_url`: the browsable `wetten.overheid.nl` page for that version.

---

## Open points

1. **Native ELI** - if/when KOOP exposes `/eli/` URIs for BWB, `eli_uri` should switch to them
   and the toestand id should move to a dedicated field.
2. **Short title (citeertitel) vs full title** - `human_readable_citation` currently uses the
   SRU `dcterms:title`. The abbreviation (afkorting, e.g. "Awb") lives in the heavy WTI file
   and is not fetched per call; a later feature may enrich the citation with it.
3. **Case law** (rechtspraak / ECLI) - a separate tool family, later.

## Evolution of the constitution

Changes to art. 1-4 follow SEMVER + an entry in `CHANGELOG.md` + a `pyproject.toml` bump.

First version: 2026-06-24. Author: Wieslaw Mazur / MateMatic.
