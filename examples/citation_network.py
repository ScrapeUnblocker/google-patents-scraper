"""Build a citation network around seed patents: edges.csv + nodes.csv for Gephi or NetworkX.

python examples/citation_network.py US9285464B2
python examples/citation_network.py US9285464B2 EP3186661B1 --family
"""

from __future__ import annotations

import argparse
import csv

from google_patents_scraper import GooglePatentsScraper, to_csv_file

parser = argparse.ArgumentParser()
parser.add_argument("numbers", nargs="*", default=["US9285464B2"])
parser.add_argument("--family", action="store_true", help="add family-to-family citations")
args = parser.parse_args()

gp = GooglePatentsScraper()  # reads SCRAPEUNBLOCKER_KEY
edges = []
for number in args.numbers:
    edges += gp.citations(number, family=args.family)  # one request per seed patent

nodes: dict[str, dict] = {}
for e in edges:
    other = e.cited if e.direction == "backward" else e.citing
    nodes.setdefault(e.patent, {"id": e.patent, "seed": True, "assignee": "", "title": ""})
    nodes.setdefault(
        other,
        {"id": other, "seed": False, "assignee": e.other_assignee, "title": e.other_title},
    )

to_csv_file(edges, "edges.csv")
with open("nodes.csv", "w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["id", "seed", "assignee", "title"])
    writer.writeheader()
    writer.writerows(nodes.values())
print(f"edges.csv: {len(edges)} citations, nodes.csv: {len(nodes)} publications")
