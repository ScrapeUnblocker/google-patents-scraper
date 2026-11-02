"""Export a company's patent portfolio to CSV, one query per priority year.

python examples/competitor_portfolio.py "Aeva"
python examples/competitor_portfolio.py "Ouster" --after 2016 --country US --granted
"""

from __future__ import annotations

import argparse
from collections import Counter

from google_patents_scraper import GooglePatentsScraper, to_csv_file

parser = argparse.ArgumentParser()
parser.add_argument("assignee", nargs="?", default="Aeva")
parser.add_argument("--after", default="2018", help="first priority year (default 2018)")
parser.add_argument("--country", action="append", help="patent office, e.g. US (repeatable)")
parser.add_argument("--granted", action="store_true", help="granted patents only")
args = parser.parse_args()

gp = GooglePatentsScraper()  # reads SCRAPEUNBLOCKER_KEY
results = gp.search(
    assignees=[args.assignee],
    after=args.after,
    countries=args.country or [],
    status="grant" if args.granted else None,
    per_year=True,  # one query per year, so big portfolios get past the 1,000-result cap
    limit=None,
)
path = f"{args.assignee.lower().replace(' ', '-')}-portfolio.csv"
to_csv_file(results, path)

by_year = Counter((r.priority_date or "")[:4] for r in results)
by_office = Counter(r.country_code for r in results)
print(f"{path}: {len(results)} publications in {gp.requests} requests")
print("by priority year:", dict(sorted(by_year.items())))
print("by office:", dict(by_office.most_common()))
