# DISCOVERY - Netherlands (BWB via KOOP SRU)

Date: 2026-06-24. Status: **BUILD** (3-tool grounding MVP shipped).

## Source

The Netherlands publishes its consolidated national legislation as the **BWB**
(Basiswettenbestand), maintained by **KOOP** (Kennis- en Exploitatiecentrum Officiële
Overheidspublicaties). It is reachable two ways, both keyless:

- **Search / metadata**: SRU 1.2 at `https://zoekservice.overheid.nl/sru/Search` with
  `x-connection=BWB`. The `explain` operation reports the `BWB Repository`
  (~146,710 records, updated daily).
- **Full text**: each version's consolidated XML lives on the official repository host
  `https://repository.officiele-overheidspublicaties.nl/bwb/<bwb_id>/...`, addressed by the
  absolute `locatie_toestand` URL returned in the SRU record.

A general KOOP repository also exists at `repository.overheid.nl/sru` (database `cup`), but its
`c.product-area` values are `datacollecties / lokalebekendmakingen / officielepublicaties /
samenwerkendecatalogi / sgd / tuchtrecht / vd` — **there is no BWB there**. Consolidated law is
only on the `x-connection=BWB` SRU above. (This is why an earlier `c.product-area==BWB` probe
returned 0.)

## Versions (toestanden)

Each act has a stable **BWB id** (e.g. `BWBR0005537` = Algemene wet bestuursrecht) and **many
time-stamped versions** (toestanden) — `dcterms.identifier=BWBR0005537` alone returns 233
records. To collapse to a single, currently-applicable version we filter by validity date:

```
overheidbwb.titel any "bestuursrecht" and overheidbwb.geldigheidsdatum=2026-06-24
```

`geldigheidsdatum=<date>` returns one record per act in force on that date (485 → 92 records,
distinct ids). The tools default `on_date` to **today**; a caller can pin any date.

## Record shape (gzd)

```
<gzd xmlns="http://standaarden.overheid.nl/sru" ...>
  <originalData>
    <overheidbwb:meta>
      <owmskern>
        <dcterms:identifier>BWBR0005537</dcterms:identifier>
        <dcterms:title>Algemene wet bestuursrecht</dcterms:title>
        <dcterms:type>wet</dcterms:type>
        <overheid:authority>Veiligheid en Justitie</overheid:authority>
        <dcterms:modified>2026-06-06</dcterms:modified>
      </owmskern>
      <bwbipm>
        <overheidbwb:toestand>http://wetten.overheid.nl/id/BWBR0005537/2026-06-04/0</overheidbwb:toestand>
        <overheidbwb:rechtsgebied>Bestuursrecht</overheidbwb:rechtsgebied>
      </bwbipm>
    </overheidbwb:meta>
  </originalData>
  <enrichedData>
    <overheidbwb:locatie_toestand>https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0005537/2026-06-04_0/xml/BWBR0005537_2026-06-04_0.xml</overheidbwb:locatie_toestand>
  </enrichedData>
</gzd>
```

## Citation contract (Art. IV)

| Field | Source | Example |
|---|---|---|
| `eli_uri` | `overheidbwb:toestand` | `http://wetten.overheid.nl/id/BWBR0005537/2026-06-04/0` |
| `human_readable_citation` | `dcterms:title` (citeertitel) | `Algemene wet bestuursrecht` |
| `source_url` | derived browsable page | `https://wetten.overheid.nl/BWBR0005537/2026-06-04` |

**ELI note (decisive).** The Netherlands has **not deployed native ELI (`/eli/`) URIs** on
consolidated BWB. None of the machine sources — the SRU gzd record, `manifest.xml`, the 23 MB
WTI, or the repository XML — carries an `/eli/` identifier; the official persistent identifier
is the `wetten.overheid.nl/id` toestand URI. Per the line rule "parse the ELI, never fabricate
it", `eli_uri` carries this equivalent stable identifier, and the connector states this
plainly in its INSTRUCTIONS, README and CONSTITUTION (the line's "say what you don't have"
freshness principle).

## Tools

- `nl_search(query, on_date=today)` — `overheidbwb.titel any "<query>" and geldigheidsdatum=<date>`,
  dedupe by `bwb_id`, return distinct acts in force.
- `nl_get_act(bwb_id, on_date=today)` — `dcterms.identifier=<id> and geldigheidsdatum=<date>`,
  one record, the citation contract.
- `nl_get_text(bwb_id, on_date=today)` — the same record → fetch `locatie_toestand` XML
  (host-restricted to the official repository).

## Open points

- Title-based search only (not full text); `geldigheidsdatum` collapses to in-force versions.
- `afkorting` (e.g. "Awb") lives only in the heavy WTI; not fetched per call — possible later
  enrichment of the citation.
- Case law (rechtspraak / ECLI) is out of scope for this MVP.
