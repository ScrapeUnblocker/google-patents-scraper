"""Scrape Google Patents through the ScrapeUnblocker ``getPageSource`` API.

:class:`GooglePatentsScraper` fetches the same pages patents.google.com loads in a
browser (the ``/xhr/query`` search JSON and the publication pages) with the
official ``scrapeunblocker`` SDK and turns them into typed records.

* Throttled, blocked and timed-out requests are retried with doubling backoff.
* A response that is not the expected JSON or patent page is fetched once more,
  then raises :class:`ParseError`.
* An unknown publication number raises :class:`NotFoundError`.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Any, Callable

from .errors import NotFoundError, ParseError, QueryError
from .models import CitationEdge, Landscape, Patent, SearchPage, SearchResult
from .parsing import is_patent_page, parse_landscape, parse_patent, parse_search
from .query import PAGE_SIZES, RESULT_CAP, PatentQuery, normalize_number, patent_url

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BrowserTimeoutError",
    "BlockedError",
    "ServerError",
    "ConnectionError",
)
_NOT_FOUND_NAMES = ("TargetNotFoundError",)
DIRECTIONS = ("backward", "forward", "both")

log = logging.getLogger(__name__)


def _is_named(error: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(error).__mro__)


def _page_size(limit: int | None) -> int:
    """The smallest page size that fits ``limit`` results in one page (max 100)."""
    if limit is None:
        return PAGE_SIZES[-1]
    for size in PAGE_SIZES:
        if limit <= size:
            return size
    return PAGE_SIZES[-1]


def build_query(query: Any = None, **filters: Any) -> PatentQuery:
    """A :class:`PatentQuery` from a query, a search term, a search URL or keyword filters.

    ``filters`` are :class:`PatentQuery` fields (``assignees=["Waymo"]``,
    ``after="2020"``, ...). A single string is accepted where a list is expected.
    """
    if isinstance(query, PatentQuery):
        base = query
    elif isinstance(query, str) and query.strip().lower().startswith(("http://", "https://")):
        base = PatentQuery.from_url(query)
    elif isinstance(query, str) and query.strip():
        base = PatentQuery(terms=[query])
    elif query is None or query == "":
        base = PatentQuery()
    else:
        raise QueryError(f"cannot build a query from {query!r}")
    changes: dict[str, Any] = {}
    for name, value in filters.items():
        if value is None:
            continue
        if not hasattr(base, name):
            raise QueryError(f"unknown search option {name!r}")
        current = getattr(base, name)
        if isinstance(current, list):
            values = [value] if isinstance(value, str) else list(value)
            changes[name] = current + [v for v in values if v]
        else:
            changes[name] = value
    return replace(base, **changes) if changes else base


class _BadPage(Exception):
    """A response without the expected data (fetched once more)."""


class GooglePatentsScraper:
    """Patent search, landscapes, full patent pages, citation graphs and monitoring.

    Args:
        api_key: Your ScrapeUnblocker API key. Defaults to the
            ``SCRAPEUNBLOCKER_KEY`` environment variable (read by the SDK).
        client: A ready ``scrapeunblocker.Client`` (or anything with a compatible
            ``get_page_source``); handy for tests.
        proxy_country: Country to route requests through (default: let the API pick).
        max_retries: Extra attempts for a request that fails transiently.
        backoff: Seconds before the first retry; doubles on each retry.
        timeout: Seconds to wait for one API response.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any = None,
        proxy_country: str | None = None,
        max_retries: int = 3,
        backoff: float = 2.0,
        timeout: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
        today: Callable[[], dt.date] = dt.date.today,
    ):
        if client is None:
            from scrapeunblocker import Client

            client = Client(api_key=api_key, timeout=timeout)
        self.client = client
        self.proxy_country = proxy_country or None
        self.max_retries = max_retries
        self.backoff = backoff
        self.sleep = sleep
        self.today = today
        #: Number of API requests made so far.
        self.requests = 0

    # -- fetching ----------------------------------------------------------------------

    def fetch(self, url: str, parse: Callable[[str], Any]) -> Any:
        """Fetch ``url`` and return ``parse(body)``.

        Transient SDK errors are retried with doubling backoff. If ``parse`` raises
        ``ValueError`` the URL is fetched once more, then :class:`ParseError` is
        raised. A 404 from Google Patents raises :class:`NotFoundError`.
        """
        attempt = 0
        bad_pages = 0
        while True:
            self.requests += 1
            try:
                try:
                    if self.proxy_country:
                        body = self.client.get_page_source(url, proxy_country=self.proxy_country)
                    else:
                        body = self.client.get_page_source(url)
                except Exception as exc:
                    if _is_named(exc, *_NOT_FOUND_NAMES):
                        raise NotFoundError(f"Google Patents answered 404 for {url}") from exc
                    raise
                try:
                    return parse(body)
                except ValueError as exc:
                    bad_pages += 1
                    if bad_pages > 1:
                        raise ParseError(f"{exc} ({url})") from None
                    raise _BadPage(str(exc)) from None
            except Exception as exc:
                retryable = isinstance(exc, _BadPage) or _is_named(exc, *_TRANSIENT_NAMES)
                if not retryable or attempt >= self.max_retries:
                    if isinstance(exc, _BadPage):
                        raise ParseError(f"{exc} ({url})") from None
                    raise
                reason = str(exc) if isinstance(exc, _BadPage) else type(exc).__name__
                log.info("retrying %s after %s", url, reason)
                self.sleep(self.backoff * (2**attempt))
                attempt += 1

    # -- search ------------------------------------------------------------------------

    def search_page(self, query: Any = None, *, page: int = 0, num: int = 100, **filters: Any):
        """One page of results (``page`` counts from 0) as a :class:`SearchPage`."""
        q = build_query(query, **filters)
        return self.fetch(q.search_url(page=page, num=num), parse_search)

    def iter_search(
        self,
        query: Any = None,
        *,
        limit: int | None = 100,
        per_year: bool = False,
        **filters: Any,
    ) -> Iterator[SearchResult]:
        """Yield results page by page, de-duplicated by publication number.

        Google serves at most 1,000 results per query. With ``per_year`` the query
        is split into one query per calendar year of its ``after``..``before``
        range, which reaches further for broad searches. ``limit=None`` collects
        everything Google serves.
        """
        q = build_query(query, **filters)
        slices = q.year_slices(today=self.today()) if per_year else [q]
        num = _page_size(limit)
        seen: set[str] = set()
        for part in slices:
            page = 0
            while True:
                result: SearchPage = self.fetch(part.search_url(page=page, num=num), parse_search)
                for row in result.results:
                    if row.publication_number in seen:
                        continue
                    seen.add(row.publication_number)
                    yield row
                    if limit is not None and len(seen) >= limit:
                        return
                page += 1
                if not result.results or page >= result.total_pages:
                    if per_year and result.total_pages * num >= RESULT_CAP:
                        log.warning(
                            "%s..%s reached Google's %d-result cap; narrow the query to see more",
                            part.after,
                            part.before,
                            RESULT_CAP,
                        )
                    break

    def search(
        self,
        query: Any = None,
        *,
        limit: int | None = 100,
        per_year: bool = False,
        **filters: Any,
    ) -> list[SearchResult]:
        """Search Google Patents.

        ``query`` is a :class:`PatentQuery`, a search term, or a patents.google.com
        search URL copied from the browser; keyword ``filters`` add to it::

            scraper.search("lidar", assignees=["Waymo"], after="2020", status="grant")
        """
        return list(self.iter_search(query, limit=limit, per_year=per_year, **filters))

    def landscape(
        self, query: Any = None, *, merge: bool = True, top: int | None = 20, **filters: Any
    ) -> Landscape:
        """Top assignees, inventors and CPC subclasses for a query, in one request.

        This is Google's own aggregation of the top-ranked matching publications;
        with ``merge`` spelling variants (``Waymo Llc`` / ``Waymo LLC``) are combined.
        """
        q = build_query(query, **filters)
        url = q.web_url()
        return self.fetch(
            q.search_url(num=10),
            lambda body: parse_landscape(body, query_url=url, merge=merge, top=top),
        )

    # -- patents -----------------------------------------------------------------------

    def patent(self, number: str, *, language: str = "en") -> Patent:
        """Every field of one publication page.

        ``number`` may be ``US9285464B2``, ``US 9,285,464 B2`` or a patents.google.com
        URL. A number without a kind code (``US9285464``) opens the publication
        Google shows for it. ``language`` picks the page language: the original
        text, or Google's machine translation (``translated_from`` tells which).
        """
        url = patent_url(number, language)
        wanted = normalize_number(number)

        def parse(body: str) -> Patent:
            if not is_patent_page(body):
                raise ValueError("expected a Google Patents publication page")
            return parse_patent(body, number=wanted, url=url)

        return self.fetch(url, parse)

    def patents(
        self, numbers: Iterable[str], *, language: str = "en", skip_missing: bool = True
    ) -> Iterator[Patent]:
        """Yield :meth:`patent` for each number; unknown numbers are logged and skipped."""
        for number in numbers:
            if not str(number).strip():
                continue
            try:
                yield self.patent(number, language=language)
            except NotFoundError:
                if not skip_missing:
                    raise
                log.warning("no Google Patents page for %s", number)

    def citations(
        self, number: str, *, direction: str = "both", family: bool = False
    ) -> list[CitationEdge]:
        """Citation edges of one publication.

        ``backward`` edges are the documents it cites, ``forward`` edges the
        documents citing it. With ``family`` the family-to-family citations Google
        lists are included too (flagged ``family_to_family``).
        """
        if direction not in DIRECTIONS:
            raise QueryError(f"direction must be one of {', '.join(DIRECTIONS)}")
        return citation_edges(self.patent(number), direction=direction, family=family)

    # -- monitoring --------------------------------------------------------------------

    def monitor(
        self,
        query: Any = None,
        *,
        state_path: str,
        days: int = 120,
        limit: int | None = RESULT_CAP,
        **filters: Any,
    ) -> list[SearchResult]:
        """Publications matching a query that were not seen on earlier runs.

        Each run searches the last ``days`` days of publications and remembers what
        it saw in the JSON file ``state_path``; the first run reports everything in
        the window. Google adds publications to its index weeks after the patent
        office publishes them, so keep the window wide: the state file makes sure
        nothing is reported twice.
        """
        q = build_query(query, **filters)
        if q.after or q.before:
            raise QueryError("monitor sets its own publication-date window; drop after/before")
        start = self.today() - dt.timedelta(days=days)
        window = replace(q, after=start.isoformat(), date_field="publication", sort="new")
        state = _load_state(state_path)
        seen: dict[str, str] = state.get("seen", {})
        fresh = [
            r for r in self.iter_search(window, limit=limit) if r.publication_number not in seen
        ]
        cutoff = start.isoformat()
        for row in fresh:
            seen[row.publication_number] = row.publication_date or cutoff
        state = {
            "query": q.web_url(),
            "updated": self.today().isoformat(),
            "seen": {k: v for k, v in sorted(seen.items()) if v >= cutoff},
        }
        _save_state(state_path, state)
        return fresh


def citation_edges(patent: Patent, *, direction: str = "both", family: bool = False):
    """:class:`CitationEdge` records for a parsed :class:`Patent`."""
    me = patent.publication_number
    groups = []
    if direction in ("backward", "both"):
        groups.append(("backward", patent.citations))
        if family:
            groups.append(("backward", patent.family_citations))
    if direction in ("forward", "both"):
        groups.append(("forward", patent.cited_by))
        if family:
            groups.append(("forward", patent.family_cited_by))
    edges = []
    for way, citations in groups:
        for c in citations:
            citing, cited = (
                (me, c.publication_number) if way == "backward" else (c.publication_number, me)
            )
            edges.append(
                CitationEdge(
                    patent=me,
                    citing=citing,
                    cited=cited,
                    direction=way,
                    family_to_family=c.family_to_family,
                    examiner_cited=c.examiner_cited,
                    third_party_cited=c.third_party_cited,
                    other_title=c.title,
                    other_assignee=c.assignee,
                    other_priority_date=c.priority_date,
                    other_publication_date=c.publication_date,
                )
            )
    return edges


def _load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except ValueError:
            raise QueryError(f"{path} is not a monitor state file") from None
    return data if isinstance(data, dict) else {}


def _save_state(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
