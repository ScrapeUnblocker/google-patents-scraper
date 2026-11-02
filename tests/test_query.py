from __future__ import annotations

import datetime as dt

import pytest
from conftest import inner_query

from google_patents_scraper import PatentQuery, QueryError, normalize_date, normalize_number
from google_patents_scraper.query import image_url, patent_url, split_number


def test_query_string_matches_the_site_format():
    q = PatentQuery(
        terms=["lidar OR radar", '"solid state"'],
        cpc=["G01S17/931", "b60w60/001"],
        assignees=["Waymo", "Aurora Operations, Inc."],
        countries=["us", "EP"],
        languages=["en", "german"],
        status="Grant",
        type="patent",
        litigation="no",
        after="2020",
        before="2021-06",
        sort="new",
    )
    text = q.query_string(page=2, num=50)
    assert text.startswith("q=(lidar+OR+radar)&q=(%22solid+state%22)&q=(CPC%3DG01S17%2F931+OR+")
    params = dict(p.split("=", 1) for p in text.split("&") if not p.startswith("q="))
    assert params == {
        "assignee": "Waymo,Aurora+Operations+Inc.",
        "before": "priority:20210630",
        "after": "priority:20200101",
        "country": "US,EP",
        "language": "ENGLISH,GERMAN",
        "status": "GRANT",
        "type": "PATENT",
        "litigation": "NO",
        "sort": "new",
        "num": "50",
        "page": "2",
    }


def test_search_url_double_encodes_the_inner_query():
    url = PatentQuery(terms=["lidar"], inventors=["Pierre-Yves Droz"]).search_url(num=10)
    assert url.startswith("https://patents.google.com/xhr/query?url=q%3D%28lidar%29")
    assert url.endswith("&exp=")
    assert inner_query(url) == {"q": ["(lidar)"], "inventor": ["Pierre-Yves Droz"], "num": ["10"]}


def test_web_url_has_no_paging():
    q = PatentQuery(terms=["(lidar)"], date_field="filing", after="2019-03-04")
    assert q.web_url() == "https://patents.google.com/?q=(lidar)&after=filing:20190304"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "at least one"),
        ({"terms": ["x"], "status": "pending"}, "unknown status"),
        ({"terms": ["x"], "sort": "newest"}, "unknown sort"),
        ({"terms": ["x"], "date_field": "grant"}, "unknown date field"),
        ({"terms": ["x"], "after": "last year"}, "bad date"),
    ],
)
def test_bad_queries(kwargs, message):
    with pytest.raises(QueryError, match=message):
        PatentQuery(**kwargs).params()


def test_page_size_must_be_supported():
    with pytest.raises(QueryError, match="page size"):
        PatentQuery(terms=["x"]).query_string(num=30)


@pytest.mark.parametrize(
    "value, end, expected",
    [
        ("2020", False, "20200101"),
        ("2020", True, "20201231"),
        ("2024-02", True, "20240229"),
        ("2024-02-10", True, "20240210"),
        ("20240210", False, "20240210"),
        (dt.date(2023, 5, 6), False, "20230506"),
    ],
)
def test_normalize_date(value, end, expected):
    assert normalize_date(value, end=end) == expected


@pytest.mark.parametrize("value", ["2020-13", "2021-02-30", "20", "May 2020"])
def test_normalize_date_rejects(value):
    with pytest.raises(QueryError):
        normalize_date(value)


def test_year_slices_cover_the_range():
    q = PatentQuery(assignees=["Waymo"], after="2019-06", before="2021-03-15")
    slices = q.year_slices()
    assert [(s.after, s.before) for s in slices] == [
        ("20190601", "20191231"),
        ("20200101", "20201231"),
        ("20210101", "20210315"),
    ]
    assert all(s.assignees == ["Waymo"] for s in slices)


def test_year_slices_default_to_today_and_need_after():
    q = PatentQuery(terms=["x"], after="2025")
    slices = q.year_slices(today=dt.date(2026, 3, 1))
    assert slices[-1].before == "20260301"
    with pytest.raises(QueryError):
        PatentQuery(terms=["x"]).year_slices()


def test_from_url_maps_known_filters():
    q = PatentQuery.from_url(
        "https://patents.google.com/?q=(lidar)&q=(rain)&assignee=Waymo+Llc,Google&country=US"
        "&before=priority:20211231&after=priority:20200101&status=GRANT&sort=new&oq=lidar"
        "&num=50&page=3&scholar"
    )
    assert q.terms == ["(lidar)", "(rain)"]
    assert q.assignees == ["Waymo Llc", "Google"]
    assert q.countries == ["US"]
    assert (q.after, q.before, q.date_field) == ("20200101", "20211231", "priority")
    assert (q.status, q.sort) == ("grant", "new")
    assert q.extra == [("scholar", "")]
    assert "page" not in q.query_string() and "oq=" not in q.query_string()


def test_from_url_keeps_mixed_date_fields_raw():
    q = PatentQuery.from_url(
        "https://patents.google.com/?q=(x)&before=filing:20200101&after=priority:20100101"
    )
    assert q.after is None and q.before is None
    assert ("before", "filing:20200101") in q.extra


def test_from_url_needs_parameters():
    with pytest.raises(QueryError):
        PatentQuery.from_url("https://patents.google.com/")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("US9285464B2", "US9285464B2"),
        ("us 9,285,464 b2", "US9285464B2"),
        ("US-9285464-B2", "US9285464B2"),
        ("patent/USD969630S1/en", "USD969630S1"),
        ("https://patents.google.com/patent/EP3186661B1/de?oq=x", "EP3186661B1"),
        ("US9285464", "US9285464"),
    ],
)
def test_normalize_number(value, expected):
    assert normalize_number(value) == expected


@pytest.mark.parametrize("value", ["", "lidar", "9285464"])
def test_normalize_number_rejects(value):
    with pytest.raises(QueryError):
        normalize_number(value)


@pytest.mark.parametrize(
    "number, parts",
    [
        ("US9285464B2", ("US", "9285464", "B2")),
        ("USD969630S1", ("US", "D969630", "S1")),
        ("USRE48042E1", ("US", "RE48042", "E1")),
        ("JPS6288906A", ("JP", "S6288906", "A")),
        ("CN208314210U", ("CN", "208314210", "U")),
        ("US9285464", ("US", "9285464", None)),
        ("nonsense", (None, None, None)),
    ],
)
def test_split_number(number, parts):
    assert split_number(number) == parts


def test_urls():
    assert patent_url("us 9285464 b2", "de") == "https://patents.google.com/patent/US9285464B2/de"
    assert image_url("8d/e5/x.pdf") == "https://patentimages.storage.googleapis.com/8d/e5/x.pdf"
    assert image_url(None) is None
