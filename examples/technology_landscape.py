"""Who is patenting a technology? Top assignees, inventors and CPC subclasses in one request.

python examples/technology_landscape.py "solid state battery" --after 2018
python examples/technology_landscape.py "perovskite solar cell" --country US
"""

from __future__ import annotations

import argparse

from google_patents_scraper import GooglePatentsScraper

parser = argparse.ArgumentParser()
parser.add_argument("terms", nargs="*", default=["solid state battery"])
parser.add_argument("--after", help="earliest priority date, e.g. 2018")
parser.add_argument("--country", action="append", help="patent office, e.g. US (repeatable)")
args = parser.parse_args()

gp = GooglePatentsScraper()  # reads SCRAPEUNBLOCKER_KEY
land = gp.landscape(terms=args.terms, after=args.after, countries=args.country or [], top=10)

print(f"Top publications analysed by Google: {land.sample_size}")
print(f"Search: {land.query_url}\n")
print("Assignees")
for f in land.assignees:
    merged = f"   (also: {', '.join(f.variants)})" if f.variants else ""
    print(f"  {f.count:4d}  {f.share:6.1%}  {f.name}{merged}")
print("\nInventors")
for f in land.inventors[:5]:
    print(f"  {f.count:4d}  {f.share:6.1%}  {f.name}")
print("\nCPC subclasses")
for f in land.cpc:
    print(f"  {f.count:4d}  {f.share:6.1%}  {f.name}")
