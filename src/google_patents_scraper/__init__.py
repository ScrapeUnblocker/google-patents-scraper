"""Scrape Google Patents through the ScrapeUnblocker API.

>>> from google_patents_scraper import GooglePatentsScraper
>>> gp = GooglePatentsScraper()  # reads SCRAPEUNBLOCKER_KEY
>>> hits = gp.search("lidar", assignees=["Waymo"], after="2020", status="grant", limit=50)
>>> [(h.publication_number, h.priority_date, h.title) for h in hits[:3]]
>>> top = gp.landscape("solid state battery", after="2018")
>>> [(f.name, f.count) for f in top.assignees[:5]]
>>> patent = gp.patent("US9285464B2")
>>> patent.legal_status, patent.expiration_date, len(patent.cited_by)
>>> [c.text[:60] for c in patent.independent_claims]
>>> edges = gp.citations("US9285464B2", direction="forward")
>>> new = gp.monitor(assignees=["Waymo"], state_path="waymo.json", days=30)

See https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import GooglePatentsError, NotFoundError, ParseError, QueryError
from .export import render, to_csv_file, write
from .models import (
    Application,
    Citation,
    CitationEdge,
    Claim,
    Classification,
    CountryStatus,
    Event,
    Facet,
    Landscape,
    LegalEvent,
    Link,
    Patent,
    Publication,
    SearchPage,
    SearchResult,
    SimilarDocument,
    WorldwideApplication,
)
from .parsing import parse_landscape, parse_patent, parse_search
from .query import (
    DATE_FIELDS,
    LANGUAGES,
    PAGE_SIZES,
    RESULT_CAP,
    PatentQuery,
    normalize_date,
    normalize_number,
    patent_url,
)
from .scraper import GooglePatentsScraper, build_query, citation_edges

__all__ = [
    "DATE_FIELDS",
    "LANGUAGES",
    "PAGE_SIZES",
    "RESULT_CAP",
    "Application",
    "Citation",
    "CitationEdge",
    "Claim",
    "Classification",
    "CountryStatus",
    "Event",
    "Facet",
    "GooglePatentsError",
    "GooglePatentsScraper",
    "Landscape",
    "LegalEvent",
    "Link",
    "NotFoundError",
    "ParseError",
    "Patent",
    "PatentQuery",
    "Publication",
    "QueryError",
    "SearchPage",
    "SearchResult",
    "SimilarDocument",
    "WorldwideApplication",
    "__version__",
    "build_query",
    "citation_edges",
    "normalize_date",
    "normalize_number",
    "parse_landscape",
    "parse_patent",
    "parse_search",
    "patent_url",
    "render",
    "to_csv_file",
    "write",
]
