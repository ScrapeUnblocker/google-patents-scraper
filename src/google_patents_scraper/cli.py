"""Command-line interface for ``google-patents-scraper``.

Commands: ``search``, ``landscape``, ``patent``, ``claims``, ``citations``, ``monitor``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from . import __version__
from .errors import GooglePatentsError, NotFoundError
from .export import FORMATS, write
from .query import DATE_FIELDS, LITIGATION, SORTS, STATUSES, TYPES, PatentQuery
from .scraper import DIRECTIONS, GooglePatentsScraper, build_query

log = logging.getLogger("google_patents_scraper")

_EXTENSIONS = {".csv": "csv", ".jsonl": "jsonl", ".json": "json", ".txt": "table"}


def _split(values: Sequence[str] | None) -> list[str]:
    """Repeatable options that also accept comma-separated values."""
    return [part.strip() for value in values or () for part in value.split(",") if part.strip()]


def _add_common(parser: argparse.ArgumentParser, *, default_format: str = "table") -> None:
    parser.add_argument(
        "-f",
        "--format",
        choices=FORMATS,
        help=f"output format (default: from the --output extension, else {default_format})",
    )
    parser.set_defaults(default_format=default_format)
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")
    parser.add_argument("--proxy-country", help="route requests through this country")
    parser.add_argument(
        "--retries", type=int, default=3, help="extra attempts per request on transient errors"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")


def _add_filters(parser: argparse.ArgumentParser, *, dates: bool = True) -> None:
    g = parser.add_argument_group("search filters")
    g.add_argument(
        "terms",
        nargs="*",
        help='search terms; each argument is one search box (AND), e.g. "lidar OR radar" rain',
    )
    g.add_argument("--url", help="a patents.google.com search URL copied from the browser")
    g.add_argument("-a", "--assignee", action="append", help="assignee name (repeatable)")
    g.add_argument("-i", "--inventor", action="append", help="inventor name (repeatable)")
    g.add_argument("--cpc", action="append", help="CPC code, e.g. G01S17/931 (repeatable)")
    g.add_argument("-c", "--country", action="append", help="patent office: US, EP, WO, CN, ...")
    g.add_argument("-l", "--language", action="append", help="document language: en, de, zh, ...")
    g.add_argument("--status", choices=STATUSES, help="granted patents or applications only")
    g.add_argument("--type", choices=TYPES, help="utility patents or design patents only")
    g.add_argument("--litigation", choices=LITIGATION, help="with or without related litigation")
    if dates:
        g.add_argument("--after", help="earliest date: YYYY, YYYY-MM or YYYY-MM-DD (inclusive)")
        g.add_argument("--before", help="latest date: YYYY, YYYY-MM or YYYY-MM-DD (inclusive)")
        g.add_argument(
            "--date-field",
            choices=DATE_FIELDS,
            default=None,
            help="date that --after/--before apply to (default priority)",
        )
    g.add_argument("--sort", choices=SORTS, help="relevance (default), new or old (filing date)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="google-patents-scraper",
        description=(
            "Scrape Google Patents search results, patent details, claims, citations "
            "and assignee landscapes via the ScrapeUnblocker API."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search patents and applications")
    _add_filters(p)
    p.add_argument("-n", "--limit", type=int, default=100, help="results to collect (default 100)")
    p.add_argument("--all", action="store_true", help="collect every result Google serves")
    p.add_argument(
        "--per-year",
        action="store_true",
        help="run one query per year of --after..--before to get past the 1,000-result cap",
    )
    p.add_argument("--print-url", action="store_true", help="print the patents.google.com URL")
    _add_common(p)

    p = sub.add_parser("landscape", help="top assignees, inventors and CPC subclasses (1 request)")
    _add_filters(p)
    p.add_argument("--top", type=int, default=20, help="entries per list (default 20)")
    p.add_argument(
        "--no-merge",
        dest="merge",
        action="store_false",
        help="keep spelling variants (Waymo Llc / Waymo LLC) apart",
    )
    _add_common(p)

    p = sub.add_parser("patent", help="full details of one or more publications")
    p.add_argument("numbers", nargs="*", help="publication numbers or patents.google.com URLs")
    p.add_argument("--from-file", help="read publication numbers from this file (one per line)")
    p.add_argument("--language", default="en", help="page language (default en)")
    p.add_argument(
        "--with-description", action="store_true", help="include the full description text"
    )
    _add_common(p, default_format="json")

    p = sub.add_parser("claims", help="the claims of a publication")
    p.add_argument("number", help="publication number or patents.google.com URL")
    p.add_argument("--language", default="en", help="page language (default en)")
    p.add_argument("--independent", action="store_true", help="independent claims only")
    _add_common(p)

    p = sub.add_parser("citations", help="citation edges (cites / cited by) of publications")
    p.add_argument("numbers", nargs="+", help="publication numbers or patents.google.com URLs")
    p.add_argument("--direction", choices=DIRECTIONS, default="both", help="default both")
    p.add_argument("--family", action="store_true", help="add family-to-family citations")
    _add_common(p)

    p = sub.add_parser("monitor", help="publications that are new since the last run")
    _add_filters(p, dates=False)
    p.add_argument("--state", required=True, help="JSON file that remembers what was seen")
    p.add_argument("--days", type=int, default=120, help="publication window in days (default 120)")
    _add_common(p)
    return parser


def _format(args: argparse.Namespace) -> str:
    if args.format:
        return args.format
    if args.output:
        ext = os.path.splitext(args.output)[1].lower()
        if ext in _EXTENSIONS:
            return _EXTENSIONS[ext]
    return args.default_format


def _query(args: argparse.Namespace) -> PatentQuery:
    base: Any = PatentQuery.from_url(args.url) if args.url else None
    filters: dict[str, Any] = {
        "terms": [t for t in args.terms if t.strip()],
        "assignees": args.assignee or [],
        "inventors": args.inventor or [],
        "cpc": _split(args.cpc),
        "countries": _split(args.country),
        "languages": _split(args.language),
        "status": args.status,
        "type": args.type,
        "litigation": args.litigation,
        "after": getattr(args, "after", None),
        "before": getattr(args, "before", None),
        "date_field": getattr(args, "date_field", None),
        "sort": args.sort,
    }
    return build_query(base, **filters)


def _numbers(args: argparse.Namespace) -> list[str]:
    numbers = list(args.numbers)
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as handle:
            numbers += [line.strip() for line in handle if line.strip() and line[0] != "#"]
    if not numbers:
        raise ValueError("give publication numbers or --from-file")
    return numbers


def _run(args: argparse.Namespace) -> int:
    scraper = GooglePatentsScraper(proxy_country=args.proxy_country, max_retries=args.retries)
    cmd = args.command
    fmt = _format(args)

    if cmd == "search":
        query = _query(args)
        if args.print_url:
            print(query.web_url(), file=sys.stderr)
        limit = None if args.all else args.limit
        results = scraper.search(query, limit=limit, per_year=args.per_year)
        log.info("%d results in %d requests", len(results), scraper.requests)
        write(results, fmt, args.output)
        return 0

    if cmd == "landscape":
        landscape = scraper.landscape(_query(args), merge=args.merge, top=args.top)
        if not landscape.sample_size:
            print("no results for this query", file=sys.stderr)
            return 1
        write(landscape, fmt, args.output)
        return 0

    if cmd == "patent":
        found = []
        for number in _numbers(args):
            try:
                patent = scraper.patent(number, language=args.language)
            except NotFoundError:
                print(f"no such publication: {number}", file=sys.stderr)
                continue
            found.append(patent if args.with_description else replace(patent, description=None))
        write(found[0] if len(found) == 1 and fmt == "json" else found, fmt, args.output)
        return 0 if found else 1

    if cmd == "claims":
        patent = scraper.patent(args.number, language=args.language)
        claims = patent.independent_claims if args.independent else patent.claims
        if not claims:
            print(
                f"{patent.publication_number} has no claims text on Google Patents", file=sys.stderr
            )
        write(claims, fmt, args.output)
        return 0

    if cmd == "citations":
        edges = []
        for number in args.numbers:
            try:
                edges += scraper.citations(number, direction=args.direction, family=args.family)
            except NotFoundError:
                print(f"no such publication: {number}", file=sys.stderr)
        write(edges, fmt, args.output)
        return 0

    if cmd == "monitor":
        first_run = not os.path.exists(args.state)
        fresh = scraper.monitor(_query(args), state_path=args.state, days=args.days)
        if first_run:
            print(
                f"first run: {len(fresh)} publications from the last {args.days} days saved "
                f"to {args.state}",
                file=sys.stderr,
            )
        else:
            print(f"{len(fresh)} new publications", file=sys.stderr)
        write(fresh, fmt, args.output)
        return 0

    raise AssertionError(f"unhandled command {cmd}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return _run(args)
    except GooglePatentsError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except ValueError as exc:
        parser.error(str(exc))
    except Exception as exc:  # SDK errors: bad key, no credit, network
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
