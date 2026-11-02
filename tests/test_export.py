from __future__ import annotations

import csv
import io
import json

import pytest

from google_patents_scraper import parse_landscape, parse_patent, parse_search, render, write
from google_patents_scraper.export import _width


def test_json_and_jsonl(search_json):
    results = parse_search(search_json).results
    data = json.loads(render(results, "json"))
    assert data[0]["publication_number"] == "JP7200378B2"
    lines = render(results, "jsonl").splitlines()
    assert len(lines) == 3 and json.loads(lines[1])["kind_code"] == "A1"


def test_csv_flattens_lists_and_dicts(search_json):
    text = render(parse_search(search_json).results, "csv")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["family_status"] == "WO=NOT_ACTIVE; US=ACTIVE"
    assert rows[1]["grant_date"] == ""


def test_landscape_csv_has_one_row_per_entry(search_json):
    rows = list(csv.DictReader(io.StringIO(render(parse_landscape(search_json), "csv"))))
    assert [(r["facet"], r["name"]) for r in rows[:2]] == [
        ("assignee", "Waymo Llc"),
        ("assignee", "Nvidia Corporation"),
    ]
    assert (rows[0]["count"], rows[0]["share"], rows[0]["variants"]) == ("63", "0.063", "Waymo LLC")


def test_tables(search_json, us_html):
    table = render(parse_search(search_json).results, "table")
    assert table.splitlines()[0].split() == [
        "publication",
        "priority",
        "published",
        "assignee",
        "title",
    ]
    patent = render(parse_patent(us_html), "table")
    assert "claims                3 (2 independent)" in patent
    assert render([], "table") == "(no results)\n"


def test_table_pads_wide_characters(search_json):
    lines = render(parse_search(search_json).results, "table").splitlines()[1:]
    # The Japanese assignee takes two columns per character, so the titles still line up.
    starts = [line.index(word) for line, word in zip(lines, ("LIDAR", "Multi", "Devices"))]
    assert len(set(starts)) > 1
    assert len({_width(line[:i]) for line, i in zip(lines, starts)}) == 1


def test_write_csv_file_has_bom(tmp_path, search_json):
    path = tmp_path / "out.csv"
    write(parse_search(search_json).results, "csv", str(path))
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_unknown_format(search_json):
    with pytest.raises(ValueError):
        render(parse_search(search_json).results, "xml")
