# Google Patents Scraper

[![CI](https://github.com/ScrapeUnblocker/google-patents-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/google-patents-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-6f42c1.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

**Scrape [Google Patents](https://patents.google.com) into clean JSON or CSV: patent search
with every filter of the search form, full patent details, claims, citations and cited-by,
patent families, legal events and assignee / inventor / CPC landscapes.**
Search by keywords, assignee, inventor, CPC code, patent office, language, status, type,
litigation and priority, filing or publication date, or paste a patents.google.com search URL
straight from your browser. For one publication you get the title, abstract, claims (with
their dependencies), description, CPC codes, inventors, original and current assignees,
priority, filing, publication, grant and expiration dates, legal status, the patent family
across countries, citations, documents citing it, family-to-family citations, similar
documents, legal events, the PDF and the drawings. Ask who is most active in a technology in
one request, export a company's portfolio year by year, build a citation network, or monitor
an assignee or CPC code for new publications.

Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos):
Google Patents has no public search API, so the `getPageSource` API fetches the same search
JSON and publication pages the patents.google.com site loads, and this package turns them
into typed records. You don't need cookies, proxies, a headless browser or retry logic of
your own.

## Features

- **Patent search.** Keywords with Google's own syntax (`OR`, `-`, `"phrases"`, `CPC=`),
  several search boxes combined with AND, assignees, inventors, CPC codes, patent offices
  (`US`, `EP`, `WO`, `CN`, `JP`, ...), document language, granted or applications only,
  utility or design patents, with or without litigation, date ranges on the priority, filing
  or publication date, and relevance / newest / oldest order.
- **Browser URLs.** Paste any patents.google.com search URL; its filters are reused as they are.
- **Paging and the 1,000-result cap.** Up to 100 results per request, de-duplicated by
  publication number. Google serves at most 1,000 results per query, so `--per-year` splits a
  date range into one query per year to export large portfolios.
- **Clean search results.** Publication number, country and kind code, title and snippet
  without highlight tags, priority / filing / publication / grant dates, first inventor and
  assignee, PDF and thumbnail URLs, number of drawings and the family's status per office.
- **Landscapes in one request.** Google's own breakdown of the top 1,000 matching
  publications: top assignees, inventors and CPC subclasses with counts and shares, with
  spelling variants (`Waymo Llc` / `Waymo LLC`) merged.
- **Full patent pages.** Title, abstract, description, claims with `depends_on` (also for
  EP and machine-translated claims that only reference "claim 1" in the text), CPC codes
  (main and additional), inventors, original and current assignees, application number,
  family ID, legal status, priority / filing / publication / grant / expiration dates,
  litigation flag, PDF and drawing URLs, prior-art keywords and external links.
- **Citations.** Patent citations and cited-by with examiner and third-party flags,
  family-to-family citations, non-patent literature and similar documents. `citations`
  turns them into a `citing -> cited` edge list for Gephi, NetworkX or pandas.
- **Families and legal history.** Priority, parent and child applications, worldwide
  applications with their status, "also published as", country status, the event timeline
  (filing, publication, grant, reassignment, expiry, litigation) and patent-office legal
  events with all their attributes.
- **Machine translations.** Non-English publications come back in Google's English
  translation without the original text mixed in, and `translated_from` says so; pass
  `--language` for the original.
- **Monitoring.** `monitor` reports publications that are new since the last run for any
  query (an assignee, a CPC code, keywords) and remembers what it saw in a small JSON file.
- **Output** as JSON, JSON Lines, CSV (Excel-friendly, UTF-8 with BOM) or a terminal table
  that keeps Chinese, Japanese and Korean names aligned.
- **Robust**: retries blocked, throttled or timed-out requests with backoff, refetches a
  response that is not the expected page, and reports unknown publication numbers cleanly.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/google-patents-scraper.git
cd google-patents-scraper
pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
and put it in the environment (or in a `.env` file you load yourself; see `.env.example`):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here        # macOS / Linux
setx SCRAPEUNBLOCKER_KEY your_key_here          # Windows (new terminals)
```

Python 3.9 or newer. The runtime dependencies are the official
[`scrapeunblocker`](https://pypi.org/project/scrapeunblocker/) SDK and `beautifulsoup4`.

## CLI usage

```bash
# Search: each positional argument is one search box; boxes are combined with AND
google-patents-scraper search "lidar OR radar" rain --country US --status grant -n 50
google-patents-scraper search lidar --assignee Waymo --after 2020 --print-url
google-patents-scraper search --cpc G01S17/931 --after 2023-01 --date-field publication -o hits.csv
google-patents-scraper search --inventor "Pierre-Yves Droz" --sort new -f jsonl

# Paste a search URL from patents.google.com (add more filters on top if you like)
google-patents-scraper search --url "https://patents.google.com/?q=(lidar)&country=US&before=priority:20100101"

# A whole portfolio, past the 1,000-results-per-query cap: one query per priority year
google-patents-scraper search --assignee "Ouster" --after 2015 --per-year --all -o ouster.csv

# Who is patenting this? Top assignees, inventors and CPC subclasses (one request)
google-patents-scraper landscape "solid state battery" --after 2018 --top 10

# Full details of publications (numbers, "US 9,285,464 B2" or URLs; JSON by default)
google-patents-scraper patent US9285464B2
google-patents-scraper patent US9285464B2 EP3186661B1 -f table
google-patents-scraper patent --from-file numbers.txt --with-description -o patents.jsonl
google-patents-scraper patent CN112731443B --language zh      # original instead of translation

# Claims only (all, or independent claims)
google-patents-scraper claims EP3186661B1 --independent

# Citation edges: what a patent cites (backward) and what cites it (forward)
google-patents-scraper citations US9285464B2 --direction forward -o cited-by.csv
google-patents-scraper citations US9285464B2 EP3186661B1 --family -o edges.csv

# New publications since the last run (run it from cron; the state file remembers)
google-patents-scraper monitor --assignee "Aeva" --state aeva.json
google-patents-scraper monitor --cpc G01S17/931 --country US --state lidar-cpc.json -o new.csv
```

Search filters (for `search`, `landscape` and `monitor`):

| Option | Meaning |
| --- | --- |
| `TERMS...` | One argument per search box, combined with AND. Inside a box Google's syntax works: `lidar OR radar`, `"solid state"`, `-drone`, `CPC=G01S17/931`. |
| `--url URL` | A patents.google.com search URL; its filters are used as they are. |
| `-a/--assignee`, `-i/--inventor` | Names (repeatable; any of them matches). |
| `--cpc CODE` | CPC codes such as `G01S17/931` (repeatable or comma-separated; any of them matches). |
| `-c/--country` | Patent offices: `US`, `EP`, `WO`, `CN`, `JP`, `KR`, `DE`, ... |
| `-l/--language` | Document language: `en`, `de`, `fr`, `es`, `zh`, `ja`, `ko`, `ru` (or Google's names). |
| `--status` | `grant` or `application`. |
| `--type` | `patent` or `design`. |
| `--litigation` | `yes` (has related litigation) or `no`. |
| `--after`, `--before` | `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, both inclusive (`--before 2020` covers all of 2020). |
| `--date-field` | Which date the range applies to: `priority` (default), `filing` or `publication`. |
| `--sort` | `relevance` (default), `new` or `old` (by filing date). |

Common options: `-n/--limit N` (default 100) or `--all`, `-f/--format json|jsonl|csv|table`
(by default taken from the `-o` file extension, else a table; `patent` defaults to JSON),
`-o/--output FILE`, `--proxy-country CC`, `--retries N`, `-v/--verbose`.

## Library usage

```python
from google_patents_scraper import GooglePatentsScraper, PatentQuery, to_csv_file

gp = GooglePatentsScraper()  # reads SCRAPEUNBLOCKER_KEY; or GooglePatentsScraper(api_key="...")

# Search with keyword filters (lists or single strings)
hits = gp.search("lidar", assignees=["Waymo"], after="2020", status="grant", limit=200)
for h in hits[:3]:
    print(h.publication_number, h.priority_date, h.assignee, h.title)
to_csv_file(hits, "waymo-lidar.csv")

# Or build the query once and reuse it (a pasted URL works too)
q = PatentQuery(terms=['"solid state" battery'], countries=["US", "EP"], after="2018")
print(q.web_url())  # open it in a browser
recent = gp.search(q, limit=None, per_year=True)  # everything, one query per year
same = gp.search("https://patents.google.com/?q=(lidar)&assignee=Waymo")

# Landscape: who files the most, in one request
land = gp.landscape("perovskite solar cell", after="2019", top=10)
for f in land.assignees:
    print(f"{f.count:4d} {f.share:6.1%} {f.name}", f.variants)

# One publication, every field
p = gp.patent("US9285464B2")
print(p.legal_status, p.expiration_date, p.current_assignees)
print([c.code for c in p.cpc if c.first])
for claim in p.independent_claims:
    print(claim.number, claim.text[:80])
print(len(p.citations), "citations;", len(p.cited_by), "cited by")

# Citation edges and a batch of patents
edges = gp.citations("US9285464B2", direction="both", family=True)
for patent in gp.patents(["US9285464B2", "EP3186661B1"]):
    print(patent.publication_number, patent.title)

# New publications since the last run
for new in gp.monitor(assignees=["Aeva"], state_path="aeva.json"):
    print(new.publication_date, new.publication_number, new.title)
```

Every record is a dataclass with `to_dict()` (nested JSON) and `to_row()` (flat CSV row).
Unknown publication numbers raise `NotFoundError`; a bad option raises `QueryError` (a
`ValueError`).

### Examples

| Script | What it does |
| --- | --- |
| [`examples/competitor_portfolio.py`](examples/competitor_portfolio.py) | A company's publications year by year to CSV, with counts per year and office. |
| [`examples/patent_report.py`](examples/patent_report.py) | One-page report: status, family, independent claims and the top citing assignees. |
| [`examples/citation_network.py`](examples/citation_network.py) | `edges.csv` + `nodes.csv` around seed patents for Gephi or NetworkX. |
| [`examples/technology_landscape.py`](examples/technology_landscape.py) | Top assignees, inventors and CPC subclasses for a technology. |

## Example output

`search lidar --assignee Waymo --after 2020 --status grant --country US -n 8`:

```text
publication   priority    published   assignee   title
US12055630B2  2020-10-15  2024-08-06  Waymo Llc  Light detection and ranging device using combined pulse and continuous optical …
US12339371B2  2021-07-06  2025-06-24  Waymo Llc  Multimode lidar receiver for coherent distance and velocity measurements
US12422529B2  2021-11-15  2025-09-23  Waymo Llc  Auto-exposure occlusion camera
US12263865B1  2022-09-08  2025-04-01  Waymo Llc  Validation of occlusions identified within autonomous vehicle driving …
US12504538B2  2021-08-04  2025-12-23  Waymo Llc  Distance-velocity disambiguation in hybrid light detection and ranging devices
US12276752B2  2021-08-16  2025-04-15  Waymo Llc  Identification of spurious radar detections in autonomous vehicle applications
US12644969B2  2020-11-02  2026-06-02  Waymo Llc  Three terminal broad area laser
US11561281B2  2020-06-29  2023-01-24  Waymo Llc  … emitters for interference mitigation in light detection and ranging (lidar) …
```

`patent US9285464B2 -f table`:

```text
field                 value
publication           US9285464B2
title                 Devices and methods for a rotating LIDAR platform with a shared transmit/receiv~
status                Ceased
assignee              Waymo LLC; Waymo Holding Inc
inventors             Gaetan Pennecot; Pierre-Yves Droz; Drew Eugene Ulrich; Daniel Gruver; Zachary M~
priority / filed      2013-08-20 / 2014-08-18
published / granted   2016-03-15 / 2016-03-15
expires               2033-08-20
cpc (first)           G01S7/481; G01S7/4813
claims                19 (2 independent)
citations / cited by  26 / 182
family                US; EP; JP; KR; CN; WO
pdf                   https://patentimages.storage.googleapis.com/b2/96/98/3e060bf3e2b8b1/US9285464.p~
```

`patent US9285464B2` (JSON, shortened):

```json
{
  "publication_number": "US9285464B2",
  "url": "https://patents.google.com/patent/US9285464B2/en",
  "title": "Devices and methods for a rotating LIDAR platform with a shared transmit/receive path",
  "country_code": "US",
  "kind_code": "B2",
  "application_number": "US14/462,075",
  "family_id": "51493404",
  "legal_status": "Ceased",
  "priority_date": "2013-08-20",
  "filing_date": "2014-08-18",
  "grant_date": "2016-03-15",
  "expiration_date": "2033-08-20",
  "original_assignees": ["Google LLC"],
  "current_assignees": ["Waymo LLC", "Waymo Holding Inc"],
  "has_litigation": true,
  "cpc": [
    {"code": "G01S7/481", "description": "Constructional features, e.g. arrangements of optical elements", "first": true, "additional": false}
  ],
  "claims_count": 19,
  "claims": [
    {"number": 2, "text": "The LIDAR device of claim 1, wherein each detector in the plurality of detectors is associated with a corresponding light source ...", "dependent": true, "depends_on": [1]}
  ],
  "citations": [
    {"publication_number": "US3790277A", "priority_date": "1971-09-20", "publication_date": "1974-02-05", "assignee": "Blount & George Inc", "title": "Optical instrument tracking system", "examiner_cited": false, "family_to_family": false}
  ],
  "legal_events": [
    {"date": "2017-03-16", "code": "AS", "title": "Assignment", "attributes": [{"label": "Owner name", "value": "WAYMO HOLDING INC., CALIFORNIA"}]}
  ]
}
```

`landscape "solid state battery" --after 2018 --top 4`:

```text
facet     name                                 count  share
assignee  宁德时代新能源科技股份有限公司       117    11.7%
assignee  GM Global Technology Operations LLC  25     2.5%
assignee  Toyota Jidosha Kabushiki Kaisha      25     2.5%
assignee  삼성에스디아이 주식회사              20     2.0%
inventor  王鹏                                 20     2.0%
inventor  哲也 浅野                            17     1.7%
inventor  章裕 酒井                            17     1.7%
inventor  Jerzy Gazda                          16     1.6%
cpc       Y02E                                 885    88.5%
cpc       H01M                                 818    81.8%
cpc       Y02P                                 314    31.4%
cpc       H01B                                 78     7.8%
```

## How it works

The patents.google.com site is a single-page app. Its search box calls a JSON endpoint,
`https://patents.google.com/xhr/query?url=<the search's query string>`, and every
publication has a server-rendered page at `/patent/<number>/<language>` whose fields carry
schema.org-style `itemprop` attributes. The scraper asks ScrapeUnblocker's `getPageSource`
for those URLs and maps them to dataclasses, so it does not depend on CSS class names.

A few things worth knowing:

- **Requests.** One request per results page (up to 100 results), per landscape and per
  publication. `--per-year` makes at least one request per year. `citations` makes one
  request per publication; `monitor` one per 100 publications in its date window.
- **The 1,000-result cap.** Google serves at most 1,000 results for one query (10 pages of
  100). A year slice that still reaches the cap is logged as a warning; narrow the query
  (country, status, CPC) to see the rest.
- **Totals.** Google's result count (`total_estimate` from `search_page`) is exact for
  narrow assignee or inventor searches but only a rough estimate for keyword searches.
  Don't use it as a patent count.
- **Names in the original language.** Search results and landscapes list inventors and
  assignees as the patent office published them, so Chinese, Japanese and Korean filings
  show names in those scripts, and the same company can appear under several names.
- **Landscapes** are Google's aggregation of the top-ranked publications for the query
  (`sample_size`, at most 1,000). Family members published in several languages are counted
  separately, so read the counts as a ranking of who is most active, not as patent totals.
- **Sort order.** `--sort new` / `old` order by filing date, and Google's relevance cut-off
  changes with the sort order, so the three orders return different sets.
- **Claims dependencies** come from the claim cross-references Google marks up, or, when a
  page has none (EP, Chinese and machine-translated claims), from "claim N" / "claims N to
  M" in the claim text (English, German, French, Spanish and Chinese).
- **Indexing delay.** Google adds publications to its index some weeks after the patent
  office publishes them. `monitor` therefore looks back 120 days by default and uses its
  state file to report each publication once.
- **Search result titles** are shortened by Google with `…` when they are long; `patent`
  returns the full title.

Please scrape responsibly: keep request rates modest, respect Google's terms, and use the
data for research, analysis and your own projects. The legal status shown by Google is its
assumption, not a legal conclusion.

## Project layout

```text
google-patents-scraper/
├── src/google_patents_scraper/
│   ├── __init__.py      # public API and __version__
│   ├── scraper.py       # GooglePatentsScraper: fetch + retries, search, landscape, patent, citations, monitor
│   ├── query.py         # PatentQuery: filters -> Google Patents query strings, URLs, dates, numbers
│   ├── parsing.py       # search JSON and publication pages -> records
│   ├── models.py        # dataclasses with to_dict / to_row / table layouts
│   ├── export.py        # JSON / JSONL / CSV / table output
│   └── cli.py           # google-patents-scraper command
├── examples/            # portfolio export, patent report, citation network, landscape
├── tests/               # offline tests with a mocked client (no API credit used)
├── pyproject.toml
├── Makefile
└── .github/workflows/ci.yml
```

## Development

```bash
pip install -e ".[dev]"
make lint      # ruff check + ruff format --check
make test      # pytest, offline
make format    # ruff format
```

The tests use trimmed copies of Google Patents responses and a fake client, so they run
without an API key or network access.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
- [ScrapeUnblocker documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
- [Python SDK on PyPI](https://pypi.org/project/scrapeunblocker/)

## License

[MIT](LICENSE) - Copyright (c) 2026 ScrapeUnblocker. This project is not affiliated with
or endorsed by Google.
