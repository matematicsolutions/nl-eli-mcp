# nl-eli-mcp - Claude plugin

Dutch law with verifiable citations, as a Claude plugin. It runs the
[nl-eli-mcp](https://github.com/matematicsolutions/nl-eli-mcp) MCP server, version 0.4.3
from PyPI. `server/uv.lock` pins that package and every dependency with hashes, and the
plugin starts it with `uv run --frozen`, so it runs exactly what was reviewed. Every
answer carries the official source, so a citation can be checked instead of trusted.

What it covers: consolidated Dutch legislation from the BWB (search by title, metadata and full text of the version in force on a chosen date, via the KOOP search service and wetten.overheid.nl), and court decisions from Rechtspraak Open Data (search by date, court and subject; full decision by ECLI). The full tool list is in the
[main README](https://github.com/matematicsolutions/nl-eli-mcp#readme).

## Requirements

Claude Code or the Claude desktop app, and [uv](https://docs.astral.sh/uv/) on your
machine (it installs the locked packages on first start and runs the server).

## Install

```
/plugin marketplace add matematicsolutions/nl-eli-mcp
/plugin install nl-eli-mcp@nl-eli-mcp
```

## Data

The server runs on your machine. Each tool call sends your query to the official Dutch source it names (the KOOP search service at zoekservice.overheid.nl, wetten.overheid.nl or Rechtspraak Open Data at data.rechtspraak.nl)
and to nothing else; nothing goes to MateMatic. Your query and the results also pass
through whatever model you use, the same way as any other message.

The standalone server can fetch a small configuration file (updated source addresses) from
this repository's GitHub Releases on first use. The plugin turns that off
(`NL_ELI_RUNTIME_URL` set to empty in `plugin.json`), so it runs only the reviewed code with
its built-in source addresses and makes no request other than the tool calls above.

Two things are written locally, in your home directory:

- a response cache (`~/.matematic/cache/nl-eli`), so a repeated lookup does not hit
  the source again. Court decisions are public records and can name the parties.
- an audit log (`~/.matematic/audit/nl-eli-mcp.jsonl`), one line per tool call: the
  tool name, a SHA-256 hash of the input (not the input itself), result size, time
  and status.

Delete either folder at any time; `NL_ELI_CACHE_DIR` and `NL_ELI_AUDIT_DIR` move them.

## Licence

Apache-2.0, see the repository's [LICENSE](https://github.com/matematicsolutions/nl-eli-mcp/blob/main/LICENSE).
