from __future__ import annotations

import datetime as dt
import json

import pytest
from conftest import (
    AuthenticationError,
    BlockedError,
    FakeClient,
    ScrapeTimeoutError,
    TargetNotFoundError,
    inner_query,
    search_body,
)

from google_patents_scraper import (
    GooglePatentsScraper,
    NotFoundError,
    ParseError,
    PatentQuery,
    QueryError,
    build_query,
    citation_edges,
    parse_patent,
)


def test_retries_transient_errors_with_backoff(search_json):
    waits = []
    answers = [BlockedError("blocked"), ScrapeTimeoutError("slow"), search_json]
    scraper = GooglePatentsScraper(client=FakeClient(answers), sleep=waits.append)
    page = scraper.search_page("lidar", num=10)
    assert len(page.results) == 3
    assert waits == [2.0, 4.0]
    assert scraper.requests == 3


def test_gives_up_after_max_retries(make_scraper):
    scraper, client = make_scraper([BlockedError("x")] * 3, max_retries=2)
    with pytest.raises(BlockedError):
        scraper.search_page("lidar")
    assert len(client.calls) == 3


def test_does_not_retry_other_sdk_errors(make_scraper):
    scraper, client = make_scraper([AuthenticationError("bad key")])
    with pytest.raises(AuthenticationError):
        scraper.search_page("lidar")
    assert len(client.calls) == 1


def test_bad_page_is_fetched_once_more_then_parse_error(make_scraper, search_json):
    scraper, client = make_scraper(["<html>captcha</html>", search_json])
    assert len(scraper.search_page("lidar").results) == 3
    scraper, client = make_scraper(["<html>captcha</html>", "<html>captcha</html>"])
    with pytest.raises(ParseError):
        scraper.search_page("lidar")
    assert len(client.calls) == 2


def test_proxy_country_is_passed_to_the_sdk(make_scraper, search_json):
    scraper, client = make_scraper([search_json], proxy_country="DE")
    scraper.search_page("lidar")
    assert client.calls[0][1] == {"proxy_country": "DE"}


def test_search_pages_until_the_limit_and_dedupes(make_scraper):
    pages = [
        search_body([f"US{i}B2" for i in range(100)], page=0, pages=5),
        search_body([f"US{i}B2" for i in range(95, 195)], page=1, pages=5),
    ]
    scraper, client = make_scraper(pages)
    results = scraper.search("lidar", limit=150)
    assert len(results) == 150
    assert len({r.publication_number for r in results}) == 150
    assert [inner_query(url)["num"] for url, _ in client.calls] == [["100"], ["100"]]
    assert "page" not in inner_query(client.calls[0][0])
    assert inner_query(client.calls[1][0])["page"] == ["1"]


def test_search_stops_at_the_last_page(make_scraper):
    pages = [
        search_body(["US1B2", "US2B2"], page=0, pages=2),
        search_body(["US3B2"], page=1, pages=2),
    ]
    scraper, client = make_scraper(pages)
    assert [r.publication_number for r in scraper.search("lidar", limit=None)] == [
        "US1B2",
        "US2B2",
        "US3B2",
    ]
    assert len(client.calls) == 2


def test_search_uses_the_smallest_page_size_for_small_limits(make_scraper):
    scraper, client = make_scraper([search_body(["US1B2"])])
    scraper.search("lidar", limit=15)
    assert inner_query(client.calls[0][0])["num"] == ["20"]


def test_search_per_year_runs_one_query_per_year(make_scraper):
    def answer(url):
        year = inner_query(url)["after"][0][len("priority:") :][:4]
        return search_body([f"US{year}A1", "US1B2"])

    scraper, client = make_scraper(answer)
    results = scraper.search(assignees=["Waymo"], after="2019", before="2021", per_year=True)
    assert [r.publication_number for r in results] == ["US2019A1", "US1B2", "US2020A1", "US2021A1"]
    dates = [(inner_query(u)["after"][0], inner_query(u)["before"][0]) for u, _ in client.calls]
    assert dates == [
        ("priority:20190101", "priority:20191231"),
        ("priority:20200101", "priority:20201231"),
        ("priority:20210101", "priority:20211231"),
    ]


def test_build_query_combines_inputs():
    q = build_query("lidar", assignees="Waymo", countries=["US"], status="grant", sort=None)
    assert (q.terms, q.assignees, q.countries, q.status) == (["lidar"], ["Waymo"], ["US"], "grant")
    url_q = build_query("https://patents.google.com/?q=(lidar)&country=EP", countries=["US"])
    assert url_q.countries == ["EP", "US"]
    base = PatentQuery(terms=["x"])
    assert build_query(base) is base
    with pytest.raises(QueryError):
        build_query("x", colour="red")


def test_landscape(make_scraper, search_json):
    scraper, client = make_scraper([search_json])
    land = scraper.landscape("lidar", top=1)
    assert land.query_url == "https://patents.google.com/?q=(lidar)"
    assert [f.name for f in land.assignees] == ["Waymo Llc"]
    assert inner_query(client.calls[0][0])["num"] == ["10"]


def test_patent_fetches_the_page(make_scraper, us_html):
    scraper, client = make_scraper([us_html])
    patent = scraper.patent("US 9,285,464 B2")
    assert client.calls[0][0] == "https://patents.google.com/patent/US9285464B2/en"
    assert patent.url == "https://patents.google.com/patent/US9285464B2/en"
    assert patent.language == "en"


def test_patent_not_found(make_scraper):
    scraper, _ = make_scraper([TargetNotFoundError("404")])
    with pytest.raises(NotFoundError):
        scraper.patent("US99999999B2")


def test_patents_skip_missing(make_scraper, us_html, ep_html):
    scraper, _ = make_scraper([us_html, TargetNotFoundError("404"), ep_html])
    found = list(scraper.patents(["US9285464B2", "US1B2", "", "EP3186661B1"]))
    assert [p.publication_number for p in found] == ["US9285464B2", "EP3186661B1"]
    scraper, _ = make_scraper([TargetNotFoundError("404")])
    with pytest.raises(NotFoundError):
        list(scraper.patents(["US1B2"], skip_missing=False))


def test_citation_edges(us_html):
    patent = parse_patent(us_html)
    edges = citation_edges(patent)
    assert [(e.citing, e.cited, e.direction) for e in edges] == [
        ("US9285464B2", "US3790277A", "backward"),
        ("US9285464B2", "US8836922B1", "backward"),
        ("US11923658B1", "US9285464B2", "forward"),
    ]
    assert edges[1].examiner_cited and edges[2].other_assignee == "Waymo Llc"
    family = citation_edges(patent, direction="forward", family=True)
    assert [(e.citing, e.family_to_family) for e in family] == [
        ("US11923658B1", False),
        ("USRE46672E1", True),
    ]


def test_citations_rejects_unknown_direction(make_scraper):
    scraper, _ = make_scraper([])
    with pytest.raises(QueryError):
        scraper.citations("US9285464B2", direction="sideways")


def test_monitor_reports_only_new_publications(make_scraper, tmp_path):
    state = tmp_path / "state.json"
    today = dt.date(2026, 11, 2)
    answers = [
        search_body(["US1A1", "US2A1"], publication_date="2026-10-20"),
        search_body(["US2A1", "US3A1"], publication_date="2026-10-27"),
    ]
    scraper, client = make_scraper(answers, today=lambda: today)
    first = scraper.monitor(assignees=["Aeva"], state_path=str(state), days=30)
    assert [r.publication_number for r in first] == ["US1A1", "US2A1"]
    second = scraper.monitor(assignees=["Aeva"], state_path=str(state), days=30)
    assert [r.publication_number for r in second] == ["US3A1"]
    inner = inner_query(client.calls[0][0])
    assert inner["after"] == ["publication:20261003"]
    assert inner["sort"] == ["new"]
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert sorted(saved["seen"]) == ["US1A1", "US2A1", "US3A1"]
    assert saved["query"] == "https://patents.google.com/?assignee=Aeva"


def test_monitor_prunes_publications_outside_the_window(make_scraper, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"seen": {"OLD1A1": "2020-01-01"}}), encoding="utf-8")
    scraper, _ = make_scraper([search_body([])], today=lambda: dt.date(2026, 11, 2))
    assert scraper.monitor("lidar", state_path=str(state)) == []
    assert json.loads(state.read_text(encoding="utf-8"))["seen"] == {}


def test_monitor_refuses_date_filters(make_scraper, tmp_path):
    scraper, _ = make_scraper([])
    with pytest.raises(QueryError):
        scraper.monitor("lidar", after="2020", state_path=str(tmp_path / "s.json"))
