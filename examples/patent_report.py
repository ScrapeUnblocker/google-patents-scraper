"""Print a one-page report for a patent: status, family, claims and who cites it.

python examples/patent_report.py US9285464B2
python examples/patent_report.py EP3186661B1
"""

from __future__ import annotations

import sys
from collections import Counter

from google_patents_scraper import GooglePatentsScraper

number = sys.argv[1] if len(sys.argv) > 1 else "US9285464B2"
p = GooglePatentsScraper().patent(number)  # reads SCRAPEUNBLOCKER_KEY

print(f"{p.publication_number}: {p.title}")
print(f"  status      {p.legal_status}  (expires {p.expiration_date or 'n/a'})")
print(f"  owner       {', '.join(p.current_assignees or p.original_assignees)}")
print(f"  priority    {p.priority_date}   filed {p.filing_date}   granted {p.grant_date or '-'}")
print(f"  main CPC    {', '.join(c.code for c in p.cpc if c.first)}")
print(f"  family      {', '.join(f'{s.country_code} ({s.documents})' for s in p.country_status)}")
print(f"  litigation  {'yes' if p.has_litigation else 'none listed'}")

print(f"\n{len(p.claims)} claims, {len(p.independent_claims)} independent:")
for claim in p.independent_claims:
    print(f"  {claim.number}. {claim.text[:150]}...")

citing = Counter(c.assignee for c in p.cited_by + p.family_cited_by if c.assignee)
print(f"\nCited by {len(p.cited_by)} publications (+{len(p.family_cited_by)} family-level).")
print("Top citing assignees:")
for name, count in citing.most_common(5):
    print(f"  {count:3d}  {name}")
