from __future__ import annotations

import csv
import datetime as dt
import json

import pytest
from conftest import FakeClient, TargetNotFoundError, inner_query, search_body

from google_patents_scraper import GooglePatentsScraper, cli


@pytest.fixture
def run(monkeypatch, capsys):
    """Run the CLI against canned responses; returns (exit code, stdout, stderr, client)."""

    def runner(argv, responses):
        client = FakeClient(responses)

        def factory(**kwargs):
            return GooglePatentsScraper(client=client, sleep=lambda s: None, **kwargs)

        monkeypatch.setattr(cli, "GooglePatentsScraper", factory)
        code = cli.main(argv)
        out = capsys.readouterr()
        return code, out.out, out.err, client

    return runner


def test_parser_search_options():
    args = cli.build_parser().parse_args(
        [
            "search",
            "lidar OR radar",
            "rain",
            "-a",
            "Waymo",
            "--cpc",
            "G01S17/931,G01S7/481",
            "-c",
            "US,EP",
            "--after",
            "2020",
            "--date-field",
            "filing",
            "--status",
            "grant",
            "--sort",
            "new",
            "-n",
            "250",
            "--per-year",
        ]
    )
    q = cli._query(args)
    assert q.terms == ["lidar OR radar", "rain"]
    assert q.cpc == ["G01S17/931", "G01S7/481"]
    assert q.countries == ["US", "EP"]
    assert (q.after, q.date_field, q.status, q.sort) == ("2020", "filing", "grant", "new")
    assert args.limit == 250 and args.per_year


def test_parser_rejects_unknown_choices():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["search", "x", "--status", "pending"])


def test_format_follows_output_extension(tmp_path):
    parser = cli.build_parser()
    args = parser.parse_args(["search", "x", "-o", str(tmp_path / "out.csv")])
    assert cli._format(args) == "csv"
    assert cli._format(parser.parse_args(["patent", "US1B2"])) == "json"
    assert cli._format(parser.parse_args(["search", "x", "-f", "jsonl"])) == "jsonl"


def test_search_command_writes_csv(run, tmp_path):
    out = tmp_path / "hits.csv"
    code, _, err, client = run(
        ["search", "lidar", "--assignee", "Waymo", "-n", "2", "-o", str(out), "--print-url"],
        [search_body(["US1B2", "US2B2", "US3B2"])],
    )
    assert code == 0
    assert "https://patents.google.com/?q=(lidar)&assignee=Waymo" in err
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert [r["publication_number"] for r in rows] == ["US1B2", "US2B2"]
    assert inner_query(client.calls[0][0])["num"] == ["10"]


def test_search_command_from_url(run):
    code, out, _, client = run(
        ["search", "--url", "https://patents.google.com/?q=(lidar)&country=US", "-f", "jsonl"],
        [search_body(["US1B2"])],
    )
    assert code == 0 and json.loads(out)["publication_number"] == "US1B2"
    assert inner_query(client.calls[0][0])["country"] == ["US"]


def test_search_without_terms_is_an_error(run):
    code, _, err, client = run(["search"], [])
    assert code == 1 and "at least one" in err and client.calls == []


def test_landscape_command(run, search_json):
    code, out, _, _ = run(["landscape", "lidar", "--top", "1"], [search_json])
    assert code == 0
    assert "Waymo Llc" in out and "Nvidia" not in out


def test_patent_command_single_json(run, us_html):
    code, out, _, _ = run(["patent", "US9285464B2"], [us_html])
    data = json.loads(out)
    assert code == 0 and data["publication_number"] == "US9285464B2"
    assert data["description"] is None


def test_patent_command_with_description_and_missing(run, us_html, tmp_path):
    numbers = tmp_path / "numbers.txt"
    numbers.write_text("# my list\nUS9285464B2\nUS1B2\n", encoding="utf-8")
    code, out, err, _ = run(
        ["patent", "--from-file", str(numbers), "--with-description", "-f", "jsonl"],
        [us_html, TargetNotFoundError("404")],
    )
    assert code == 0
    assert json.loads(out.splitlines()[0])["description"].startswith("BACKGROUND")
    assert "no such publication: US1B2" in err


def test_claims_command(run, us_html):
    code, out, _, _ = run(["claims", "US9285464B2", "--independent", "-f", "json"], [us_html])
    assert code == 0 and [c["number"] for c in json.loads(out)] == [1, 3]


def test_citations_command(run, us_html):
    code, out, _, _ = run(["citations", "US9285464B2", "--direction", "forward"], [us_html])
    assert code == 0
    assert "US11923658B1" in out and "US3790277A" not in out


def test_monitor_command(run, tmp_path):
    state = tmp_path / "s.json"
    published = (dt.date.today() - dt.timedelta(days=5)).isoformat()
    code, _, err, _ = run(
        ["monitor", "--assignee", "Aeva", "--state", str(state)],
        [search_body(["US1A1"], publication_date=published)],
    )
    assert code == 0 and "first run: 1 publications" in err
    code, _, err, _ = run(
        ["monitor", "--assignee", "Aeva", "--state", str(state)],
        [search_body(["US1A1"], publication_date=published)],
    )
    assert code == 0 and "0 new publications" in err


def test_sdk_errors_exit_1(run):
    class AuthenticationError(Exception):
        pass

    code, _, err, _ = run(["patent", "US1B2"], [AuthenticationError("invalid key")])
    assert code == 1 and "AuthenticationError: invalid key" in err
