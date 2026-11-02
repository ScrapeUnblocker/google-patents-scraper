"""Build Google Patents search queries and patent URLs.

:class:`PatentQuery` holds the filters of the patents.google.com search form and
turns them into the query string the site sends to its own search endpoint
(``/xhr/query``). Every filter here was checked against live results; anything
else can be passed through untouched with ``extra`` (or by pasting a search URL
into :meth:`PatentQuery.from_url`).
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass, field, replace
from urllib.parse import parse_qsl, quote, quote_plus, unquote, urlsplit

from .errors import QueryError

BASE_URL = "https://patents.google.com"
SEARCH_ENDPOINT = BASE_URL + "/xhr/query"
#: Base URL of the patent PDFs, drawings and thumbnails Google Patents links to.
IMAGE_BASE = "https://patentimages.storage.googleapis.com/"

#: Results per page the search endpoint accepts.
PAGE_SIZES = (10, 20, 50, 100)
#: Google Patents serves at most this many results for one query.
RESULT_CAP = 1000

#: ``--sort`` value -> Google ``sort`` parameter. ``new``/``old`` order by filing date.
SORTS = {"relevance": None, "new": "new", "old": "old"}
#: Date the ``before``/``after`` filters apply to.
DATE_FIELDS = ("priority", "filing", "publication")
STATUSES = {"grant": "GRANT", "application": "APPLICATION"}
TYPES = {"patent": "PATENT", "design": "DESIGN"}
LITIGATION = {"yes": "YES", "no": "NO"}
#: Document language filter. Keys are ISO 639-1 codes; Google takes the English name.
LANGUAGES = {
    "en": "ENGLISH",
    "de": "GERMAN",
    "fr": "FRENCH",
    "es": "SPANISH",
    "zh": "CHINESE",
    "ja": "JAPANESE",
    "ko": "KOREAN",
    "ru": "RUSSIAN",
}

# Characters left as they are inside the inner query string, the way the site sends it.
_SAFE = "():,"
_NUMBER_RE = re.compile(r"^([A-Z]{2})([A-Z]{0,2}\d[0-9A-Z]*?)([A-Z]\d?)?$")
_URL_NUMBER_RE = re.compile(r"(?:^|/)patent/([^/?#]+)")
_DATE_RE = re.compile(r"^(\d{4})(?:-?(\d{2}))?(?:-?(\d{2}))?$")


def _choice(value: str | None, table: dict, name: str) -> str | None:
    if value is None or value == "":
        return None
    key = str(value).strip().lower()
    if key not in table:
        raise QueryError(f"unknown {name} {value!r}; choose from {', '.join(table)}")
    return table[key]


def normalize_language(value: str) -> str:
    """``de`` / ``german`` / ``GERMAN`` -> ``GERMAN`` (other names pass through upper-cased)."""
    text = value.strip()
    if not text:
        raise QueryError("empty language")
    return LANGUAGES.get(text.lower(), text.upper())


def normalize_date(value: str | dt.date, *, end: bool = False) -> str:
    """A date as Google's ``YYYYMMDD``.

    ``2020``, ``2020-06``, ``2020-06-15``, ``20200615`` and :class:`datetime.date` are
    accepted. A year or month alone means its first day, or its last day when
    ``end`` is true (so ``before=2020`` covers all of 2020).
    """
    if isinstance(value, dt.date):
        return value.strftime("%Y%m%d")
    match = _DATE_RE.match(str(value).strip())
    if not match:
        raise QueryError(f"bad date {value!r}; use YYYY, YYYY-MM or YYYY-MM-DD")
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else (12 if end else 1)
    if not 1 <= month <= 12:
        raise QueryError(f"bad month in {value!r}")
    if match.group(3):
        day = int(match.group(3))
    else:
        day = calendar.monthrange(year, month)[1] if end else 1
    try:
        return dt.date(year, month, day).strftime("%Y%m%d")
    except ValueError:
        raise QueryError(f"bad date {value!r}") from None


def _group(term: str) -> str:
    term = term.strip()
    if term.startswith("(") and term.endswith(")"):
        return term
    return f"({term})"


def _names(values: list[str]) -> str:
    # Google separates several assignees / inventors with commas, so a comma inside
    # one name ("Aurora Operations, Inc.") would split it in two.
    cleaned = [re.sub(r"\s+", " ", v.replace(",", " ")).strip() for v in values]
    return ",".join(v for v in cleaned if v)


@dataclass
class PatentQuery:
    """A Google Patents search.

    Args:
        terms: Search terms. Each entry is one search box: entries are combined with
            AND, and Google's own syntax works inside one (``lidar OR radar``,
            ``"solid state"``, ``-drone``, ``CPC=G01S17/931``).
        assignees: Assignee names (any of them matches).
        inventors: Inventor names (any of them matches).
        cpc: CPC classification codes such as ``G01S17/931`` (any of them matches).
        countries: Patent office codes such as ``US``, ``EP``, ``WO``, ``CN``.
        languages: Document languages (``en``, ``de``, ``zh``, ... or Google's names).
        status: ``grant`` or ``application``.
        type: ``patent`` or ``design``.
        litigation: ``yes`` (has related litigation) or ``no``.
        after: Earliest date (``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``), inclusive.
        before: Latest date, inclusive.
        date_field: The date ``after``/``before`` apply to: priority, filing, publication.
        sort: ``relevance`` (default), ``new`` or ``old`` (by filing date).
        extra: Raw ``(name, value)`` parameters appended as they are.
    """

    terms: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    inventors: list[str] = field(default_factory=list)
    cpc: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    status: str | None = None
    type: str | None = None
    litigation: str | None = None
    after: str | None = None
    before: str | None = None
    date_field: str = "priority"
    sort: str = "relevance"
    extra: list[tuple[str, str]] = field(default_factory=list)

    # -- building --------------------------------------------------------------------

    def params(self) -> list[tuple[str, str]]:
        """The query as ``(name, value)`` pairs, without paging."""
        if self.date_field not in DATE_FIELDS:
            raise QueryError(
                f"unknown date field {self.date_field!r}; choose from {', '.join(DATE_FIELDS)}"
            )
        if self.sort not in SORTS:
            raise QueryError(f"unknown sort {self.sort!r}; choose from {', '.join(SORTS)}")
        pairs: list[tuple[str, str]] = [("q", _group(t)) for t in self.terms if t.strip()]
        codes = [c.strip().upper() for c in self.cpc if c.strip()]
        if codes:
            pairs.append(("q", "(" + " OR ".join(f"CPC={c}" for c in codes) + ")"))
        if self.assignees:
            pairs.append(("assignee", _names(self.assignees)))
        if self.inventors:
            pairs.append(("inventor", _names(self.inventors)))
        if self.before:
            pairs.append(("before", f"{self.date_field}:{normalize_date(self.before, end=True)}"))
        if self.after:
            pairs.append(("after", f"{self.date_field}:{normalize_date(self.after)}"))
        if self.countries:
            pairs.append(("country", ",".join(c.strip().upper() for c in self.countries)))
        if self.languages:
            pairs.append(("language", ",".join(normalize_language(x) for x in self.languages)))
        for name, value, table in (
            ("status", self.status, STATUSES),
            ("type", self.type, TYPES),
            ("litigation", self.litigation, LITIGATION),
        ):
            choice = _choice(value, table, name)
            if choice:
                pairs.append((name, choice))
        if SORTS[self.sort]:
            pairs.append(("sort", SORTS[self.sort]))
        pairs.extend(self.extra)
        if not any(name in ("q", "assignee", "inventor") for name, _ in pairs):
            raise QueryError("give at least one search term, assignee, inventor or CPC code")
        return pairs

    def query_string(self, *, page: int = 0, num: int = 10) -> str:
        """The search as Google Patents' own query string (``q=(lidar)&num=10``)."""
        if num not in PAGE_SIZES:
            raise QueryError(f"page size must be one of {', '.join(map(str, PAGE_SIZES))}")
        pairs = self.params()
        pairs.append(("num", str(num)))
        if page:
            pairs.append(("page", str(page)))
        return "&".join(f"{name}={quote_plus(value, safe=_SAFE)}" for name, value in pairs)

    def search_url(self, *, page: int = 0, num: int = 10) -> str:
        """URL of the JSON search endpoint for one results page."""
        inner = self.query_string(page=page, num=num)
        return f"{SEARCH_ENDPOINT}?url={quote(inner, safe='')}&exp="

    def web_url(self) -> str:
        """The same search on patents.google.com, to open in a browser."""
        pairs = self.params()
        return BASE_URL + "/?" + "&".join(f"{n}={quote_plus(v, safe=_SAFE)}" for n, v in pairs)

    def year_slices(self, *, today: dt.date | None = None) -> list[PatentQuery]:
        """One copy of the query per calendar year between ``after`` and ``before``.

        A single query returns at most :data:`RESULT_CAP` results; slicing by year
        reaches past that cap for broad searches. ``after`` is required; ``before``
        defaults to today.
        """
        if not self.after:
            raise QueryError("splitting by year needs an 'after' date")
        start = normalize_date(self.after)
        end = normalize_date(self.before, end=True) if self.before else None
        if end is None:
            end = (today or dt.date.today()).strftime("%Y%m%d")
        if end < start:
            raise QueryError("'before' is earlier than 'after'")
        slices = []
        for year in range(int(start[:4]), int(end[:4]) + 1):
            lo = max(start, f"{year}0101")
            hi = min(end, f"{year}1231")
            slices.append(replace(self, after=lo, before=hi))
        return slices

    # -- parsing ---------------------------------------------------------------------

    @classmethod
    def from_url(cls, url: str) -> PatentQuery:
        """A query from a patents.google.com search URL copied from the browser.

        Known filters are mapped onto fields; anything else is kept in ``extra``.
        Paging (``page``, ``num``) and the display-only ``oq`` are dropped.
        """
        parts = urlsplit(url.strip())
        text = parts.query or (parts.path if "=" in parts.path else "")
        if not text:
            raise QueryError(f"no search parameters in {url!r}")
        query = cls()
        dates: dict[str, tuple[str, str]] = {}
        for name, value in parse_qsl(text, keep_blank_values=True):
            if name in ("page", "num", "oq", "exp"):
                continue
            if name == "q":
                query.terms.append(value)
            elif name == "assignee":
                query.assignees.extend(v for v in value.split(",") if v.strip())
            elif name == "inventor":
                query.inventors.extend(v for v in value.split(",") if v.strip())
            elif name == "country":
                query.countries.extend(v for v in value.split(",") if v.strip())
            elif name == "language":
                query.languages.extend(v for v in value.split(",") if v.strip())
            elif name in ("status", "type", "litigation"):
                setattr(query, name, value.lower())
            elif name == "sort" and value in ("new", "old"):
                query.sort = value
            elif name in ("before", "after") and ":" in value:
                kind, _, date = value.partition(":")
                dates[name] = (kind, date)
            else:
                query.extra.append((name, value))
        kinds = {kind for kind, _ in dates.values()}
        if len(kinds) == 1 and kinds <= set(DATE_FIELDS):
            query.date_field = kinds.pop()
            for name, (_, date) in dates.items():
                setattr(query, name, date)
        else:
            query.extra.extend((name, f"{kind}:{date}") for name, (kind, date) in dates.items())
        return query


def normalize_number(value: str) -> str:
    """A publication number from user input.

    Accepts ``US9285464B2``, ``US 9,285,464 B2``, ``US-9285464-B2``,
    ``patent/US9285464B2/en`` and full patents.google.com URLs.
    """
    text = unquote(str(value)).strip()
    match = _URL_NUMBER_RE.search(text)
    if match:
        text = match.group(1)
    number = re.sub(r"[\s,\-./]", "", text).upper()
    if not _NUMBER_RE.match(number):
        raise QueryError(f"not a publication number: {value!r}")
    return number


def split_number(number: str) -> tuple[str | None, str | None, str | None]:
    """``US9285464B2`` -> ``("US", "9285464", "B2")``; parts that are missing are None."""
    match = _NUMBER_RE.match(number or "")
    if not match:
        return None, None, None
    return match.group(1), match.group(2), match.group(3)


def patent_url(number: str, language: str = "en") -> str:
    """The patents.google.com page of a publication."""
    return f"{BASE_URL}/patent/{normalize_number(number)}/{language}"


def image_url(path: str | None) -> str | None:
    """A full URL for the relative PDF / image paths in search results."""
    if not path:
        return None
    if path.startswith("http"):
        return path
    return IMAGE_BASE + path.lstrip("/")
