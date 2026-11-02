"""Typed records returned by the scraper.

Every record is a dataclass with ``to_dict()`` (nested, JSON-ready) and
``to_row()`` (flat, CSV-ready). Missing values are ``None`` rather than empty
strings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class _Record:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[call-overload]

    def to_row(self) -> dict[str, Any]:
        """A flat dict for CSV: lists are joined with ``; ``, nested records dropped."""
        row: dict[str, Any] = {}
        for key, value in self.to_dict().items():
            if isinstance(value, list):
                if all(not isinstance(v, (dict, list)) for v in value):
                    row[key] = "; ".join(str(v) for v in value)
            elif isinstance(value, dict):
                if all(not isinstance(v, (dict, list)) for v in value.values()):
                    row[key] = "; ".join(f"{k}={v}" for k, v in value.items())
            else:
                row[key] = value
        return row


# -- search ----------------------------------------------------------------------------


@dataclass
class SearchResult(_Record):
    """One search hit.

    ``inventor`` and ``assignee`` are the first names Google lists, in the
    original language of the document (Japanese, Chinese, ...).
    ``family_status`` maps each patent office in the family to ``ACTIVE`` or
    ``NOT_ACTIVE``.
    """

    publication_number: str
    title: str | None = None
    url: str | None = None
    country_code: str | None = None
    kind_code: str | None = None
    language: str | None = None
    rank: int | None = None
    priority_date: str | None = None
    filing_date: str | None = None
    publication_date: str | None = None
    grant_date: str | None = None
    is_granted: bool = False
    inventor: str | None = None
    assignee: str | None = None
    snippet: str | None = None
    pdf_url: str | None = None
    thumbnail_url: str | None = None
    figure_count: int = 0
    family_status: dict[str, str] = field(default_factory=dict)

    TABLE_HEADER = ("publication", "priority", "published", "assignee", "title")

    def table_row(self) -> tuple[str, ...]:
        return (
            self.publication_number,
            self.priority_date or "",
            self.publication_date or "",
            (self.assignee or "")[:30],
            self.title or "",
        )


@dataclass
class SearchPage(_Record):
    """One page of search results.

    ``total_estimate`` is the count Google reports. It is exact for narrow
    assignee or inventor searches but only a rough estimate for keyword searches,
    so do not use it as a patent count. ``total_pages`` is how many pages Google
    will actually serve (at most 1,000 results per query).
    """

    results: list[SearchResult]
    page: int = 0
    total_pages: int = 0
    total_estimate: int | None = None


@dataclass
class Facet(_Record):
    """One assignee, inventor or CPC subclass in a :class:`Landscape`.

    ``share`` is ``count`` divided by the landscape's ``sample_size``.
    ``variants`` lists spellings that were merged into this entry
    (``Waymo Llc`` / ``Waymo LLC``).
    """

    name: str
    count: int
    share: float | None = None
    variants: list[str] = field(default_factory=list)


@dataclass
class Landscape(_Record):
    """Google's own breakdown of the top publications matching a query.

    Google aggregates up to ``sample_size`` top-ranked publications (family
    members in several languages count separately), so treat the counts as a
    ranking of who is most active rather than as patent totals.
    """

    query_url: str
    sample_size: int
    assignees: list[Facet] = field(default_factory=list)
    inventors: list[Facet] = field(default_factory=list)
    cpc: list[Facet] = field(default_factory=list)
    related_landscapes: list[str] = field(default_factory=list)

    TABLE_HEADER = ("facet", "name", "count", "share")

    def _facets(self) -> list[tuple[str, Facet]]:
        return (
            [("assignee", f) for f in self.assignees]
            + [("inventor", f) for f in self.inventors]
            + [("cpc", f) for f in self.cpc]
        )

    def table_rows(self) -> list[tuple[str, ...]]:
        return [
            (kind, f.name, str(f.count), f"{f.share:.1%}" if f.share is not None else "")
            for kind, f in self._facets()
        ]

    def csv_rows(self) -> list[dict[str, Any]]:
        """One CSV row per assignee, inventor and CPC subclass."""
        return [{"facet": kind, **f.to_row()} for kind, f in self._facets()]


# -- patent page -----------------------------------------------------------------------


@dataclass
class Claim(_Record):
    """One claim. ``depends_on`` lists the claims it refers back to."""

    number: int
    text: str
    dependent: bool = False
    depends_on: list[int] = field(default_factory=list)

    TABLE_HEADER = ("claim", "depends on", "text")

    def table_row(self) -> tuple[str, ...]:
        return (str(self.number), ", ".join(map(str, self.depends_on)) or "-", self.text)


@dataclass
class Classification(_Record):
    """A CPC code. ``first`` marks the codes Google lists first (the main ones);
    ``additional`` marks additional (non-inventive) codes."""

    code: str
    description: str | None = None
    first: bool = False
    additional: bool = False


@dataclass
class Citation(_Record):
    """A citing or cited publication.

    ``family_to_family`` is true for citations Google lists between whole patent
    families rather than this exact publication.
    """

    publication_number: str
    url: str | None = None
    language: str | None = None
    priority_date: str | None = None
    publication_date: str | None = None
    assignee: str | None = None
    title: str | None = None
    examiner_cited: bool = False
    third_party_cited: bool = False
    family_to_family: bool = False


@dataclass
class SimilarDocument(_Record):
    publication_number: str | None
    url: str | None = None
    publication_date: str | None = None
    title: str | None = None
    is_patent: bool = True


@dataclass
class Application(_Record):
    """An application related to this patent (priority, parent, child, family)."""

    application_number: str | None
    publication_number: str | None = None
    url: str | None = None
    priority_date: str | None = None
    filing_date: str | None = None
    title: str | None = None
    status: str | None = None
    relation: str | None = None


@dataclass
class WorldwideApplication(_Record):
    """One application of the family in any country (the "Worldwide applications" list)."""

    application_number: str | None
    country_code: str | None = None
    filing_date: str | None = None
    publication_number: str | None = None
    url: str | None = None
    status: str | None = None
    status_category: str | None = None


@dataclass
class Publication(_Record):
    """Another publication of the same invention ("Also published as")."""

    publication_number: str
    url: str | None = None
    publication_date: str | None = None
    language: str | None = None


@dataclass
class CountryStatus(_Record):
    country_code: str
    documents: int | None = None
    representative: str | None = None
    this_country: bool = False


@dataclass
class Event(_Record):
    """A timeline entry: priority, filing, publication, grant, reassignment, expiry, litigation."""

    type: str | None
    title: str | None
    date: str | None = None
    critical: bool = False
    link: str | None = None


@dataclass
class LegalEvent(_Record):
    """A patent-office legal event. ``attributes`` keeps every label/value pair in order."""

    date: str | None
    code: str | None = None
    title: str | None = None
    attributes: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Link(_Record):
    """An external link (USPTO, Espacenet, Global Dossier, ...)."""

    name: str | None
    url: str


@dataclass
class Patent(_Record):
    """Everything on a Google Patents publication page.

    ``translated_from`` names the original language when Google machine-translated
    the text (for example ``Chinese`` on an ``/en`` page); the original-language
    text is dropped so fields hold one language only.
    """

    publication_number: str
    url: str
    language: str | None = None
    translated_from: str | None = None
    title: str | None = None
    abstract: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    number: str | None = None
    kind_code: str | None = None
    publication_type: str | None = None
    application_number: str | None = None
    family_id: str | None = None
    legal_status: str | None = None
    priority_date: str | None = None
    filing_date: str | None = None
    publication_date: str | None = None
    grant_date: str | None = None
    expiration_date: str | None = None
    inventors: list[str] = field(default_factory=list)
    original_assignees: list[str] = field(default_factory=list)
    current_assignees: list[str] = field(default_factory=list)
    has_litigation: bool = False
    pdf_url: str | None = None
    images: list[str] = field(default_factory=list)
    cpc: list[Classification] = field(default_factory=list)
    claims_count: int | None = None
    claims: list[Claim] = field(default_factory=list)
    description: str | None = None
    prior_art_keywords: list[str] = field(default_factory=list)
    prior_art_date: str | None = None
    citations: list[Citation] = field(default_factory=list)
    family_citations: list[Citation] = field(default_factory=list)
    cited_by: list[Citation] = field(default_factory=list)
    family_cited_by: list[Citation] = field(default_factory=list)
    non_patent_citations: list[str] = field(default_factory=list)
    similar_documents: list[SimilarDocument] = field(default_factory=list)
    priority_applications: list[Application] = field(default_factory=list)
    applications_claiming_priority: list[Application] = field(default_factory=list)
    parent_applications: list[Application] = field(default_factory=list)
    child_applications: list[Application] = field(default_factory=list)
    family_applications: list[Application] = field(default_factory=list)
    worldwide_applications: list[WorldwideApplication] = field(default_factory=list)
    also_published_as: list[Publication] = field(default_factory=list)
    country_status: list[CountryStatus] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    legal_events: list[LegalEvent] = field(default_factory=list)
    landscapes: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    TABLE_HEADER = ("field", "value")

    @property
    def independent_claims(self) -> list[Claim]:
        return [c for c in self.claims if not c.dependent]

    def table_rows(self) -> list[tuple[str, ...]]:
        rows = [
            ("publication", self.publication_number),
            ("title", self.title or ""),
            ("status", self.legal_status or ""),
            ("assignee", "; ".join(self.current_assignees or self.original_assignees)),
            ("inventors", "; ".join(self.inventors)),
            ("priority / filed", f"{self.priority_date or '-'} / {self.filing_date or '-'}"),
            ("published / granted", f"{self.publication_date or '-'} / {self.grant_date or '-'}"),
            ("expires", self.expiration_date or ""),
            ("cpc (first)", "; ".join(c.code for c in self.cpc if c.first)),
            ("claims", f"{len(self.claims)} ({len(self.independent_claims)} independent)"),
            ("citations / cited by", f"{len(self.citations)} / {len(self.cited_by)}"),
            ("family", "; ".join(s.country_code for s in self.country_status)),
            ("pdf", self.pdf_url or ""),
        ]
        return [r for r in rows if r[1]]

    def to_row(self) -> dict[str, Any]:
        """One flat CSV row with counts instead of the long lists."""
        row = {
            k: v
            for k, v in super().to_row().items()
            if k not in ("description", "images", "non_patent_citations")
        }
        row["cpc"] = "; ".join(c.code for c in self.cpc)
        row["first_cpc"] = "; ".join(c.code for c in self.cpc if c.first)
        row["independent_claims"] = len(self.independent_claims)
        row["citations"] = len(self.citations)
        row["cited_by"] = len(self.cited_by)
        row["family_cited_by"] = len(self.family_cited_by)
        row["family_size"] = len(self.also_published_as) + 1
        row["countries"] = "; ".join(s.country_code for s in self.country_status)
        return row


@dataclass
class CitationEdge(_Record):
    """One edge of a citation graph: ``citing`` cites ``cited``.

    ``direction`` is ``backward`` when ``patent`` (the publication you asked
    about) is the citing one and ``forward`` when it is the cited one. The
    ``other_*`` fields describe the publication at the other end.
    """

    patent: str
    citing: str
    cited: str
    direction: str
    family_to_family: bool = False
    examiner_cited: bool = False
    third_party_cited: bool = False
    other_title: str | None = None
    other_assignee: str | None = None
    other_priority_date: str | None = None
    other_publication_date: str | None = None

    TABLE_HEADER = ("citing", "cited", "direction", "other assignee", "other title")

    def table_row(self) -> tuple[str, ...]:
        direction = self.direction + (" (family)" if self.family_to_family else "")
        return (
            self.citing,
            self.cited,
            direction,
            (self.other_assignee or "")[:30],
            self.other_title or "",
        )
