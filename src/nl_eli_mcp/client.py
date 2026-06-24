"""Async httpx client for the Dutch BWB consolidated-law SRU API (KOOP) with cache.

KOOP serves consolidated Dutch legislation (BWB) over SRU 1.2 at
``zoekservice.overheid.nl/sru/Search`` with ``x-connection=BWB`` (keyless). The full
consolidated text of each version lives on the official repository host as XML; we fetch it
by the absolute ``locatie_toestand`` URL returned in the SRU record. We keep our own backoff
and cache.
"""

from __future__ import annotations

from urllib.parse import urlparse

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://zoekservice.overheid.nl/sru/Search"
REPOSITORY_HOST = "repository.officiele-overheidspublicaties.nl"
SRU_VERSION = "1.2"
SRU_CONNECTION = "BWB"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "nl-eli-mcp/0.1.0 (+https://github.com/matematicsolutions/nl-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


def _sanitize_terms(terms: str) -> str:
    """Strip CQL-breaking double quotes; collapse whitespace."""
    return " ".join(terms.replace('"', " ").split())


class NlError(Exception):
    """Raised when the BWB SRU response cannot be retrieved or is invalid."""


class KoopBwbClient:
    """Async client for the KOOP BWB SRU API. Use as ``async with KoopBwbClient() as c: ...``."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/xml"},
            follow_redirects=True,
        )

    async def __aenter__(self) -> KoopBwbClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get(self, url: str, *, params: dict[str, str] | None, category: str) -> str:
        cache_key = url if not params else url + "?" + httpx.QueryParams(params).__str__()
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, str):
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                self._cache.set(cache_key, resp.text, ttl=HttpCache.ttl_for(category))
                return resp.text
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def _search(self, cql: str, *, maximum_records: int, category: str) -> str:
        params = {
            "x-connection": SRU_CONNECTION,
            "operation": "searchRetrieve",
            "version": SRU_VERSION,
            "query": cql,
            "maximumRecords": str(maximum_records),
            "startRecord": "1",
        }
        return await self._get(self.base_url, params=params, category=category)

    async def search_by_title(self, terms: str, on_date: str, *, maximum_records: int) -> str:
        """Search acts whose title matches ``terms`` and that are in force on ``on_date``."""
        safe = _sanitize_terms(terms)
        cql = f'overheidbwb.titel any "{safe}" and overheidbwb.geldigheidsdatum={on_date}'
        return await self._search(cql, maximum_records=maximum_records, category="search")

    async def get_version_record(self, bwb_id: str, on_date: str) -> str:
        """SRU record for the version of ``bwb_id`` in force on ``on_date``."""
        cql = f"dcterms.identifier={bwb_id} and overheidbwb.geldigheidsdatum={on_date}"
        return await self._search(cql, maximum_records=1, category="act")

    async def fetch_text(self, text_url: str) -> str:
        """Fetch the consolidated XML by its absolute repository URL (host-restricted)."""
        host = (urlparse(text_url).hostname or "").lower()
        if host != REPOSITORY_HOST:
            raise NlError(f"refusing to fetch text from unexpected host: {host!r}")
        return await self._get(text_url, params=None, category="act")
