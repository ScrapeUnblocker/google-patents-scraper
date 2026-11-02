"""Shared fixtures: a fake SDK client and trimmed copies of real Google Patents responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from google_patents_scraper import GooglePatentsScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# Exceptions named like the SDK's: the scraper matches them by class name, so the
# tests do not depend on the SDK's constructor signatures.
class BlockedError(Exception):
    pass


class ScrapeTimeoutError(Exception):
    pass


class TargetNotFoundError(Exception):
    pass


class AuthenticationError(Exception):
    pass


def inner_query(url: str) -> dict[str, list[str]]:
    """The decoded Google Patents query string inside a ``/xhr/query`` URL."""
    outer = parse_qs(urlsplit(url).query)
    return parse_qs(unquote(outer["url"][0]))


def search_body(numbers: list[str], *, page: int = 0, pages: int = 1, **patent: Any) -> str:
    """A minimal search JSON with one result per publication number."""
    results = [
        {
            "id": f"patent/{n}/en",
            "rank": i,
            "patent": {"publication_number": n, "title": f"Title {n}", **patent},
        }
        for i, n in enumerate(numbers)
    ]
    return json.dumps(
        {
            "results": {
                "total_num_results": 999,
                "total_num_pages": pages,
                "num_page": page,
                "cluster": [{"result": results}] if results else [{}],
            }
        }
    )


class FakeClient:
    """Answers ``get_page_source`` from a list of responses or a function of the URL."""

    def __init__(self, responses: list[Any] | Callable[[str], Any]):
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def get_page_source(self, url: str, **kwargs: Any) -> str:
        self.calls.append((url, kwargs))
        if callable(self.responses):
            answer = self.responses(url)
        else:
            answer = self.responses.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.fixture
def make_scraper():
    def factory(responses, **kwargs: Any):
        client = FakeClient(responses)
        scraper = GooglePatentsScraper(client=client, sleep=lambda s: None, **kwargs)
        return scraper, client

    return factory


@pytest.fixture
def us_html() -> str:
    return load("patent_us.html")


@pytest.fixture
def cn_html() -> str:
    return load("patent_cn_translated.html")


@pytest.fixture
def ep_html() -> str:
    return load("patent_ep.html")


@pytest.fixture
def search_json() -> str:
    return load("search.json")
