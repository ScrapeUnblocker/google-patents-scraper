from __future__ import annotations

import pytest

from google_patents_scraper import parse_landscape, parse_patent, parse_search
from google_patents_scraper.parsing import _referenced_claims, clean_text, decode_json


def test_clean_text_strips_highlight_tags_and_entities():
    assert clean_text(" <b>LIDAR</b> receiver &hellip;") == "LIDAR receiver …"
    assert clean_text("") is None
    assert clean_text(None) is None


def test_decode_json_accepts_pre_wrapped_json():
    data = decode_json('<html><body><pre>{"results": {"cluster": []}}</pre></body></html>')
    assert data == {"results": {"cluster": []}}


@pytest.mark.parametrize("body", ["<html><body>Sorry...</body></html>", "not json", "[]", "{}"])
def test_decode_json_rejects_other_bodies(body):
    with pytest.raises(ValueError):
        decode_json(body)


def test_parse_search_results(search_json):
    page = parse_search(search_json)
    assert page.total_pages == 3
    assert page.total_estimate == 126711
    assert [r.publication_number for r in page.results] == [
        "JP7200378B2",
        "US20240183952A1",
        "US9285464B2",
    ]
    jp = page.results[0]
    assert jp.title == "LIDAR receiver with multiple detectors to reduce range ambiguity"
    assert jp.snippet.endswith("claim 1 …")
    assert jp.url == "https://patents.google.com/patent/JP7200378B2/en"
    assert (jp.country_code, jp.kind_code) == ("JP", "B2")
    assert jp.is_granted is True
    assert jp.pdf_url == (
        "https://patentimages.storage.googleapis.com/8d/e5/aa/f00a30486f4ce5/JP7200378B2.pdf"
    )
    assert jp.figure_count == 2
    assert jp.family_status == {"WO": "NOT_ACTIVE", "US": "ACTIVE"}
    app = page.results[1]
    assert app.is_granted is False and app.grant_date is None
    assert app.assignee == "Guilin University Of Technology"
    assert app.snippet == "A bathymetry LiDAR & storage system"
    assert app.kind_code == "A1"


def test_parse_search_empty_cluster():
    page = parse_search('{"results": {"total_num_results": 0, "cluster": [{}], "summary": {}}}')
    assert page.results == [] and page.total_pages == 0


def test_parse_landscape_merges_spelling_variants(search_json):
    land = parse_landscape(search_json, query_url="https://patents.google.com/?q=(lidar)")
    assert land.sample_size == 1000
    waymo = land.assignees[0]
    assert (waymo.name, waymo.count, waymo.variants) == ("Waymo Llc", 63, ["Waymo LLC"])
    assert waymo.share == 0.063
    droz = land.inventors[0]
    assert (droz.name, droz.count, droz.variants) == ("Pierre-Yves Droz", 38, ["Droz Pierre-Yves"])
    assert [f.name for f in land.cpc] == ["G01S", "G06T"]
    assert land.related_landscapes == ["Engineering & Computer Science", "Physics & Mathematics"]


def test_parse_landscape_without_merge_and_top(search_json):
    land = parse_landscape(search_json, merge=False, top=2)
    assert [f.name for f in land.assignees] == ["Waymo Llc", "Nvidia Corporation"]
    assert len(land.inventors) == 2


def test_parse_patent_header_and_dates(us_html):
    p = parse_patent(us_html, url="https://patents.google.com/patent/US9285464B2/en")
    assert p.publication_number == "US9285464B2"
    assert p.language == "en" and p.translated_from is None
    assert (
        p.title
        == "Devices and methods for a rotating LIDAR platform with a shared transmit/receive path"
    )
    assert (
        p.abstract
        == "A LIDAR device may transmit light pulses originating from one or more light sources."
    )
    assert (p.country_code, p.country_name, p.number, p.kind_code) == (
        "US",
        "United States",
        "9285464",
        "B2",
    )
    assert p.publication_type == "Patent (having previously published pre-grant publication)"
    assert p.application_number == "US14/462,075"
    assert p.family_id == "51493404"
    assert p.legal_status == "Ceased"
    assert (p.priority_date, p.filing_date) == ("2013-08-20", "2014-08-18")
    assert (p.publication_date, p.grant_date) == ("2016-03-15", "2016-03-15")
    assert p.expiration_date == "2033-08-20"
    assert p.inventors == ["Gaetan Pennecot", "Pierre-Yves Droz"]
    assert p.original_assignees == ["Google LLC"]
    assert p.current_assignees == ["Waymo LLC"]
    assert p.has_litigation is True
    assert p.pdf_url.endswith("/US9285464.pdf")
    assert p.images == [
        "https://patentimages.storage.googleapis.com/4c/9d/0d/5dc47e48fd22e0/US09285464-20160315-D00000.png"
    ]
    assert p.prior_art_keywords == ["light", "lidar device"]
    assert p.landscapes == ["Engineering & Computer Science", "Remote Sensing"]
    assert [link.name for link in p.links] == ["USPTO PatentCenter", "Espacenet"]


def test_parse_patent_claims_and_description(us_html):
    p = parse_patent(us_html)
    assert p.claims_count == 3
    assert [(c.number, c.dependent, c.depends_on) for c in p.claims] == [
        (1, False, []),
        (2, True, [1]),
        (3, False, []),
    ]
    assert p.claims[0].text.startswith("A light detection and ranging (LIDAR) device, comprising:")
    assert p.claims[1].text == "The LIDAR device of claim 1, wherein the lens is curved."
    assert [c.number for c in p.independent_claims] == [1, 3]
    assert p.description == (
        "BACKGROUND\n\nVehicles can be configured to operate in an autonomous mode.\n\n"
        "One such sensor is a light detection and ranging (LIDAR) device."
    )


def test_parse_patent_cpc(us_html):
    cpc = {c.code: c for c in parse_patent(us_html).cpc}
    assert list(cpc) == ["G01S7/481", "G01S17/931"]
    assert cpc["G01S7/481"].first and not cpc["G01S7/481"].additional
    assert cpc["G01S17/931"].additional and not cpc["G01S17/931"].first
    assert cpc["G01S7/481"].description.startswith("Constructional features")


def test_parse_patent_citations(us_html):
    p = parse_patent(us_html)
    assert [c.publication_number for c in p.citations] == ["US3790277A", "US8836922B1"]
    first, second = p.citations
    assert first.assignee == "Blount & George Inc" and not first.examiner_cited
    assert second.examiner_cited and not second.family_to_family
    assert first.url == "https://patents.google.com/patent/US3790277A/en"
    assert p.family_citations[0].family_to_family and p.family_citations[0].examiner_cited
    assert p.cited_by[0].publication_number == "US11923658B1"
    assert p.family_cited_by[0].third_party_cited
    assert p.non_patent_citations == [
        "International Search Report dated Nov. 19, 2014 of PCT/US2014/047864."
    ]


def test_parse_patent_family_and_events(us_html):
    p = parse_patent(us_html)
    assert p.priority_applications[0].publication_number == "US9285464B2"
    parent = p.parent_applications[0]
    assert (parent.application_number, parent.relation) == ("US13/971,606", "Continuation")
    assert p.family_applications[0].status == "Active"
    world = p.worldwide_applications[0]
    assert (world.country_code, world.publication_number, world.status) == (
        "EP",
        "EP3036562B1",
        "Active",
    )
    assert [(s.country_code, s.documents, s.this_country) for s in p.country_status] == [
        ("US", 5, True),
        ("EP", 2, False),
    ]
    assert p.also_published_as[0].publication_number == "KR102095895B1"
    assert p.similar_documents[0].is_patent
    litigation = p.events[0]
    assert (litigation.type, litigation.date, litigation.critical) == ("litigation", None, True)
    assert litigation.link.startswith("https://portal.unifiedpatents.com/")
    event = p.legal_events[0]
    assert (event.code, event.title) == ("AS", "Assignment")
    assert [a["value"] for a in event.attributes] == [
        "WAYMO HOLDING INC., CALIFORNIA",
        "WAYMO LLC, CALIFORNIA",
    ]


def test_parse_patent_drops_original_text_of_translations(cn_html):
    p = parse_patent(cn_html)
    assert p.translated_from == "Chinese"
    assert p.claims[0].text == (
        "A three-dimensional imaging method, characterized in that: "
        "the single-photon detector acquires data;"
    )
    assert [(c.number, c.depends_on) for c in p.claims] == [(1, []), (2, [1]), (3, [1, 2])]
    assert p.description == (
        "technical field\n\nThe invention belongs to the technical field of imaging laser radar."
    )
    assert "技" not in p.description  # no Chinese characters left
    assert p.inventors == ["刘俊良"]
    assert p.non_patent_citations == []


def test_parse_patent_ep_claims_reference_in_text(ep_html):
    p = parse_patent(ep_html)
    assert [(c.number, c.dependent, c.depends_on) for c in p.claims] == [
        (1, False, []),
        (2, True, [1]),
        (3, True, [1, 2]),
    ]
    assert p.publication_date == "2021-04-07"
    assert p.abstract is None
    assert p.description.startswith("BACKGROUND\n\nThere are generally two types")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("The device of claim 3, wherein", {3}),
        ("A method according to any one of claims 2 to 4", {2, 3, 4}),
        ("Einrichtung nach Anspruch 1, wobei", {1}),
        ("Dispositif selon la revendication 2", {2}),
        ("根据权利要求4-7任一项所述的系统", {4, 5, 6, 7}),
        ("根据权利要求1所述的方法", {1}),
        ("A lidar system comprising a laser", set()),
    ],
)
def test_referenced_claims(text, expected):
    assert _referenced_claims(text) == expected


def test_parse_patent_rejects_other_pages():
    with pytest.raises(ValueError):
        parse_patent("<html><body>Our systems have detected unusual traffic</body></html>")


def test_patent_flat_row(us_html):
    row = parse_patent(us_html).to_row()
    assert row["publication_number"] == "US9285464B2"
    assert row["cpc"] == "G01S7/481; G01S17/931"
    assert row["first_cpc"] == "G01S7/481"
    assert (row["citations"], row["cited_by"], row["independent_claims"]) == (2, 1, 2)
    assert row["family_size"] == 2
    assert row["inventors"] == "Gaetan Pennecot; Pierre-Yves Droz"
    assert "description" not in row and "claims" not in row
