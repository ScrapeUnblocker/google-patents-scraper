"""Turn Google Patents responses into records.

* Search: the JSON of ``/xhr/query`` (``results.cluster[].result[].patent``).
* Landscape: the ``results.summary`` block of the same JSON.
* Patent: the publication page, which marks every field with schema.org-style
  ``itemprop`` attributes, so no CSS class names are involved.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from .models import (
    Application,
    Citation,
    Claim,
    Classification,
    CountryStatus,
    Event,
    Facet,
    Landscape,
    LegalEvent,
    Link,
    Patent,
    Publication,
    SearchPage,
    SearchResult,
    SimilarDocument,
    WorldwideApplication,
)
from .query import BASE_URL, image_url, split_number

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_PRE_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.S | re.I)
_CLAIM_NO_RE = re.compile(r"^\s*\d+\s*[.)]\s*")
# "claim 1" in English, German, French, Spanish and Chinese claim text, with "to 4" ranges.
_CLAIM_REF_RES = (
    re.compile(
        r"\b(?:claims?|anspr(?:uch|üche)|revendications?|reivindicaci(?:ón|ones))\s+(\d+)"
        r"(?:\s*(?:-|to|through|bis|à|a)\s*(\d+))?",
        re.I,
    ),
    re.compile(r"(?:权利要求|權利要求)\s*(\d+)(?:\s*(?:-|~|至|到)\s*(\d+))?"),
)
_DIGITS_RE = re.compile(r"\d+")
_BLOCK_CLASSES = {"description-paragraph", "description-line"}


# -- text helpers ----------------------------------------------------------------------


def clean_text(value: Any) -> str | None:
    """Strip tags (Google highlights matches with ``<b>``), unescape and collapse spaces."""
    if value is None:
        return None
    text = html_lib.unescape(_TAG_RE.sub("", str(value)))
    text = _SPACE_RE.sub(" ", text).strip()
    return text or None


def _tidy(text: str) -> str:
    text = _SPACE_RE.sub(" ", text).strip()
    text = re.sub(r"\s+([,.;:!?)\]])", r"\1", text)
    return re.sub(r"([(\[])\s+", r"\1", text)


def _text(el: Tag | None) -> str | None:
    if el is None:
        return None
    return _tidy(el.get_text(" ", strip=True)) or None


def _prop(scope: Tag, name: str, tag: str | None = None) -> Tag | None:
    if tag:
        return scope.find(tag, attrs={"itemprop": name})
    return scope.find(attrs={"itemprop": name})


def _props(scope: Tag, name: str, tag: str | None = None) -> list[Tag]:
    if tag:
        return scope.find_all(tag, attrs={"itemprop": name})
    return scope.find_all(attrs={"itemprop": name})


def _prop_text(scope: Tag, name: str) -> str | None:
    return _text(_prop(scope, name))


def _date(scope: Tag, name: str) -> str | None:
    el = _prop(scope, name)
    if el is None:
        return None
    return (el.get("datetime") or "").strip() or _text(el)


def _flag(scope: Tag, name: str) -> bool:
    el = _prop(scope, name)
    if el is None:
        return False
    content = el.get("content")
    return content is None or str(content).strip().lower() == "true"


def _link(scope: Tag) -> str | None:
    a = scope.find("a", href=True)
    if a is None:
        return None
    href = a["href"]
    return BASE_URL + href if href.startswith("/") else href


def _int(value: Any) -> int | None:
    match = _DIGITS_RE.search(str(value or ""))
    return int(match.group()) if match else None


# -- search ----------------------------------------------------------------------------


def decode_json(body: Any) -> dict:
    """The search JSON, also when it arrives wrapped in an HTML ``<pre>`` block."""
    if isinstance(body, dict):
        return body
    text = str(body or "").strip()
    if text.startswith("<"):
        match = _PRE_RE.search(text)
        if not match:
            raise ValueError("expected search JSON, got an HTML page")
        text = html_lib.unescape(match.group(1)).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("expected search JSON, got something else") from None
    if not isinstance(data, dict) or not isinstance(data.get("results"), dict):
        raise ValueError("search JSON has no 'results' object")
    return data


def _family_status(patent: dict) -> dict[str, str]:
    meta = (patent.get("family_metadata") or {}).get("aggregated") or {}
    status = {}
    for item in meta.get("country_status") or []:
        code = item.get("country_code")
        state = (item.get("best_patent_stage") or {}).get("state")
        if code and state:
            status[code] = state
    return status


def parse_result(item: dict) -> SearchResult | None:
    """One entry of ``results.cluster[].result[]``."""
    patent = item.get("patent") or {}
    number = clean_text(patent.get("publication_number"))
    doc_id = str(item.get("id") or "")
    if not number and doc_id.startswith("patent/"):
        number = doc_id.split("/")[1]
    if not number:
        return None
    country, _, kind = split_number(number)
    language = clean_text(patent.get("language"))
    if doc_id.startswith("patent/"):
        url = f"{BASE_URL}/{doc_id}"
    else:
        url = f"{BASE_URL}/patent/{number}/{language or 'en'}"
    grant = clean_text(patent.get("grant_date"))
    return SearchResult(
        publication_number=number,
        title=clean_text(patent.get("title")),
        url=url,
        country_code=country,
        kind_code=kind,
        language=language,
        rank=item.get("rank") if isinstance(item.get("rank"), int) else None,
        priority_date=clean_text(patent.get("priority_date")),
        filing_date=clean_text(patent.get("filing_date")),
        publication_date=clean_text(patent.get("publication_date")),
        grant_date=grant,
        is_granted=grant is not None,
        inventor=clean_text(patent.get("inventor")),
        assignee=clean_text(patent.get("assignee")),
        snippet=clean_text(patent.get("snippet")),
        pdf_url=image_url(patent.get("pdf")),
        thumbnail_url=image_url(patent.get("thumbnail")),
        figure_count=len(patent.get("figures") or []),
        family_status=_family_status(patent),
    )


def parse_search(data: Any) -> SearchPage:
    """A :class:`SearchPage` from the search JSON (or its raw text)."""
    data = decode_json(data)
    results = data["results"]
    rows = []
    for cluster in results.get("cluster") or []:
        for item in (cluster or {}).get("result") or []:
            row = parse_result(item)
            if row is not None:
                rows.append(row)
    total = results.get("total_num_results")
    return SearchPage(
        results=rows,
        page=int(results.get("num_page") or 0),
        total_pages=int(results.get("total_num_pages") or 0),
        total_estimate=total if isinstance(total, int) else None,
    )


# -- landscape -------------------------------------------------------------------------


def _name_key(name: str) -> str:
    # "Waymo LLC" / "Waymo Llc" and "Droz Pierre-Yves" / "Pierre-Yves Droz" share a key.
    words = re.findall(r"\w+", name.casefold())
    return " ".join(sorted(words)) or name.casefold()


def _facets(items: list[dict], sample: int, *, merge: bool, top: int | None) -> list[Facet]:
    merged: dict[str, list[dict]] = {}
    for item in items:
        name = clean_text(item.get("key"))
        if not name or name == "Total" or not isinstance(item.get("value"), int):
            continue
        key = _name_key(name) if merge else name
        merged.setdefault(key, []).append({**item, "key": name})
    facets = []
    for group in merged.values():
        group.sort(key=lambda i: -i["value"])
        count = sum(i["value"] for i in group)
        facets.append(
            Facet(
                name=group[0]["key"],
                count=count,
                share=round(count / sample, 4) if sample else None,
                variants=[i["key"] for i in group[1:]],
            )
        )
    facets.sort(key=lambda f: (-f.count, f.name))
    return facets[:top] if top else facets


def parse_landscape(
    data: Any, *, query_url: str = "", merge: bool = True, top: int | None = None
) -> Landscape:
    """Top assignees, inventors and CPC subclasses from the search JSON ``summary``.

    With ``merge`` (the default) spellings that differ only in case, punctuation
    or word order are combined into one entry.
    """
    results = decode_json(data)["results"]
    summary = results.get("summary") or {}
    totals = [i for i in summary.get("assignee") or [] if i.get("key") == "Total"]
    sample = totals[0]["value"] if totals and isinstance(totals[0].get("value"), int) else 0
    related = (results.get("landscape") or {}).get("related_landscapes") or []
    return Landscape(
        query_url=query_url,
        sample_size=sample,
        assignees=_facets(summary.get("assignee") or [], sample, merge=merge, top=top),
        inventors=_facets(summary.get("inventor") or [], sample, merge=merge, top=top),
        cpc=_facets(summary.get("cpc") or [], sample, merge=False, top=top),
        related_landscapes=[clean_text(r.get("name")) for r in related if r.get("name")],
    )


# -- patent page -----------------------------------------------------------------------


def is_patent_page(html: str) -> bool:
    return 'itemprop="publicationNumber"' in html or "itemprop='publicationNumber'" in html


def _citation(row: Tag, *, family: bool) -> Citation | None:
    number = _prop_text(row, "publicationNumber")
    if not number:
        return None
    marks = _prop_text(row, "examinerCited") or ""
    assignee = _prop(row, "assigneeOriginal")
    return Citation(
        publication_number=number,
        url=_link(row),
        language=_prop_text(row, "primaryLanguage"),
        priority_date=_date(row, "priorityDate"),
        publication_date=_date(row, "publicationDate"),
        assignee=_text(assignee),
        title=_prop_text(row, "title"),
        examiner_cited="*" in marks,
        third_party_cited="†" in marks,
        family_to_family=family,
    )


def _citations(soup: Tag, name: str, *, family: bool = False) -> list[Citation]:
    rows = (_citation(row, family=family) for row in _props(soup, name, "tr"))
    return [c for c in rows if c is not None]


def _applications(soup: Tag, name: str) -> list[Application]:
    out = []
    for row in _props(soup, name, "tr"):
        out.append(
            Application(
                application_number=_prop_text(row, "applicationNumber"),
                publication_number=_prop_text(row, "representativePublication"),
                url=_link(row),
                priority_date=_date(row, "priorityDate"),
                filing_date=_date(row, "filingDate"),
                title=_prop_text(row, "title"),
                status=_prop_text(row, "ifiStatus"),
                relation=_prop_text(row, "relationType"),
            )
        )
    return out


def _last_int(value: Any) -> int | None:
    # Claim ids look like CLM-00002, c-en-01-0002 or cl0002: the claim is the last number.
    numbers = _DIGITS_RE.findall(str(value or ""))
    return int(numbers[-1]) if numbers else None


def _referenced_claims(text: str) -> set[int]:
    """Claim numbers a claim refers to in its text ("of claim 1", "claims 2 to 4")."""
    found: set[int] = set()
    for pattern in _CLAIM_REF_RES:
        for match in pattern.finditer(text[:400]):
            first = int(match.group(1))
            last = int(match.group(2)) if match.group(2) else first
            if last - first > 50:
                last = first
            found.update(range(first, last + 1))
    return found


def _claims(soup: Tag) -> list[Claim]:
    section = _prop(soup, "claims", "section")
    if section is None:
        return []
    nodes = [
        el
        for el in section.find_all(attrs={"num": True})
        if el.name == "claim" or "claim" in (el.get("class") or [])
    ]
    claims = []
    seen: set[int] = set()
    for el in nodes:
        number = _last_int(el.get("num"))
        text = _text(el)
        if number is None or not text or number in seen:
            continue
        seen.add(number)
        text = _CLAIM_NO_RE.sub("", text)
        refs = {_last_int(ref.get("idref")) for ref in el.find_all("claim-ref")}
        refs.discard(None)
        if not refs:
            refs = _referenced_claims(text)
        depends = sorted(r for r in refs if r is not None and r < number)
        claims.append(Claim(number=number, text=text, dependent=bool(depends), depends_on=depends))
    return claims


def _is_block(el: Tag) -> bool:
    classes = el.get("class") or []
    return el.name in ("heading", "p") or bool(_BLOCK_CLASSES.intersection(classes))


def _description(soup: Tag) -> str | None:
    section = _prop(soup, "description", "section")
    if section is None:
        return None
    content = _prop(section, "content") or section
    blocks = []
    for el in content.find_all(_is_block):
        if el.find_parent(_is_block):
            continue
        text = _text(el)
        if text:
            blocks.append(text)
    if not blocks:
        text = _text(content)
        if text and text.lower().startswith("description"):
            text = text[len("description") :].strip()
        return text or None
    return "\n\n".join(blocks)


def _classifications(soup: Tag) -> list[Classification]:
    found: dict[str, Classification] = {}
    for li in _props(soup, "classifications", "li"):
        if not _flag(li, "Leaf") or li.find("li", attrs={"itemprop": "classifications"}):
            continue
        code = _prop_text(li, "Code")
        if not code:
            continue
        entry = found.setdefault(code, Classification(code=code))
        entry.description = entry.description or _prop_text(li, "Description")
        entry.first = entry.first or _flag(li, "FirstCode")
        entry.additional = entry.additional or _flag(li, "Additional")
    return list(found.values())


def _events(soup: Tag) -> list[Event]:
    out = []
    for dd in _props(soup, "events", "dd"):
        out.append(
            Event(
                type=_prop_text(dd, "type"),
                title=_prop_text(dd, "title"),
                date=_date(dd, "date"),
                critical=_flag(dd, "critical"),
                link=_prop_text(dd, "externalLink"),
            )
        )
    return out


def _legal_events(soup: Tag) -> list[LegalEvent]:
    out = []
    for row in _props(soup, "legalEvents", "tr"):
        attributes = []
        for p in _props(row, "attributes"):
            label, value = _prop_text(p, "label"), _prop_text(p, "value")
            if label or value:
                attributes.append({"label": label or "", "value": value or ""})
        out.append(
            LegalEvent(
                date=_date(row, "date"),
                code=_prop_text(row, "code"),
                title=_prop_text(row, "title"),
                attributes=attributes,
            )
        )
    return out


def _worldwide(soup: Tag) -> list[WorldwideApplication]:
    out = []
    for li in _props(soup, "application", "li"):
        doc = _prop_text(li, "documentId") or ""
        parts = doc.split("/")
        out.append(
            WorldwideApplication(
                application_number=_prop_text(li, "applicationNumber"),
                country_code=_prop_text(li, "countryCode"),
                filing_date=_date(li, "filingDate"),
                publication_number=parts[1] if len(parts) > 1 else None,
                url=_link(li),
                status=_prop_text(li, "legalStatus"),
                status_category=_prop_text(li, "legalStatusCat"),
            )
        )
    return out


def _similar(soup: Tag) -> list[SimilarDocument]:
    out = []
    for row in _props(soup, "similarDocuments", "tr"):
        out.append(
            SimilarDocument(
                publication_number=_prop_text(row, "publicationNumber"),
                url=_link(row),
                publication_date=_date(row, "publicationDate"),
                title=_prop_text(row, "title"),
                is_patent=_flag(row, "isPatent"),
            )
        )
    return out


def _publications(soup: Tag) -> list[Publication]:
    out = []
    for row in _props(soup, "docdbFamily", "tr"):
        number = _prop_text(row, "publicationNumber")
        if number:
            out.append(
                Publication(
                    publication_number=number,
                    url=_link(row),
                    publication_date=_date(row, "publicationDate"),
                    language=_prop_text(row, "primaryLanguage"),
                )
            )
    return out


def _country_status(soup: Tag) -> list[CountryStatus]:
    out = []
    for row in _props(soup, "countryStatus", "tr"):
        code = _prop_text(row, "countryCode")
        if code:
            out.append(
                CountryStatus(
                    country_code=code,
                    documents=_int(_prop_text(row, "num")),
                    representative=_prop_text(row, "representativePublication"),
                    this_country=_flag(row, "thisCountry"),
                )
            )
    return out


def _meta(soup: Tag, name: str, scheme: str | None = None) -> list[str]:
    out = []
    for m in soup.find_all("meta", attrs={"name": name}):
        if scheme and m.get("scheme") != scheme:
            continue
        value = _tidy(m.get("content") or "")
        if value:
            out.append(value)
    return out


def _content(soup: Tag, name: str) -> str | None:
    el = _prop(soup, name, "meta")
    return _tidy(el.get("content") or "") or None if el is not None else None


def _event_date(events: list[Event], kind: str, contains: str = "") -> str | None:
    for event in events:
        if event.type == kind and event.date and contains.lower() in (event.title or "").lower():
            return event.date
    return None


def parse_patent(html: str, *, number: str | None = None, url: str | None = None) -> Patent:
    """A :class:`Patent` from a publication page.

    Raises ``ValueError`` when the page is not a Google Patents publication page.
    """
    if not is_patent_page(html):
        raise ValueError("not a Google Patents publication page")
    soup = BeautifulSoup(html, "html.parser")
    # Machine-translated pages repeat the original text next to the translation.
    for original in soup.select("span.google-src-text"):
        original.decompose()
    header = soup.find("dl") or soup
    publication = _prop_text(header, "publicationNumber") or number or ""
    language = None
    if url:
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        language = tail if len(tail) == 2 else None
    title = (_meta(soup, "DC.title") or [None])[0]
    if not title:
        heading = _prop_text(soup, "pageTitle") or ""
        title = heading.split(" - ", 1)[-1].rsplit(" - Google Patents", 1)[0].strip() or None
    abstract_section = _prop(soup, "abstract", "section")
    abstract = None
    if abstract_section is not None:
        abstract = _text(_prop(abstract_section, "content") or abstract_section)
    application = _prop(soup, "application", "section")
    metadata = _prop(application, "metadata") if application is not None else None
    family = _prop(soup, "family", "section")
    family_id = None
    if family is not None:
        for h2 in family.find_all("h2"):
            match = re.match(r"\s*ID=(\d+)", h2.get_text())
            if match:
                family_id = match.group(1)
                break
    events = _events(soup)
    expiration = None
    for event in events:
        if event.date and "expiration" in (event.title or "").lower():
            expiration = event.date
    publication_date = _event_date(events, "publication", publication)
    if publication_date is None:
        issued = _meta(soup, "DC.date", "issue")
        publication_date = issued[0] if issued else None
    claims_section = _prop(soup, "claims", "section")
    status = _prop(soup, "legalStatusIfi")
    country, number_part, kind = split_number(publication)
    return Patent(
        publication_number=publication,
        url=url or f"{BASE_URL}/patent/{publication}/{language or 'en'}",
        language=language,
        translated_from=_prop_text(soup, "translatedLanguage"),
        title=title,
        abstract=abstract,
        country_code=_prop_text(header, "countryCode") or country,
        country_name=_prop_text(header, "countryName"),
        number=_content(soup, "numberWithoutCodes") or number_part,
        kind_code=_content(soup, "kindCode") or kind,
        publication_type=_content(soup, "publicationDescription"),
        application_number=_prop_text(metadata, "applicationNumber") if metadata else None,
        family_id=family_id,
        legal_status=_prop_text(status, "status") if status is not None else None,
        priority_date=(_date(metadata, "priorityDate") if metadata else None)
        or _date(soup, "priorArtDate"),
        filing_date=(_date(metadata, "filingDate") if metadata else None)
        or _event_date(events, "filed"),
        publication_date=publication_date,
        grant_date=_event_date(events, "granted"),
        expiration_date=expiration,
        inventors=[t for t in (_text(d) for d in _props(soup, "inventor", "dd")) if t],
        original_assignees=[
            t for t in (_text(d) for d in _props(soup, "assigneeOriginal", "dd")) if t
        ],
        current_assignees=[
            t for t in (_text(d) for d in _props(soup, "assigneeCurrent", "dd")) if t
        ],
        has_litigation=_flag(soup, "hasLitigation"),
        pdf_url=(_prop(soup, "pdfLink", "a") or {}).get("href") or None,
        images=[
            m.get("content")
            for li in _props(soup, "images", "li")
            for m in [_prop(li, "full", "meta")]
            if m is not None and m.get("content")
        ],
        cpc=_classifications(soup),
        claims_count=_int(_prop_text(claims_section, "count")) if claims_section else None,
        claims=_claims(soup),
        description=_description(soup),
        prior_art_keywords=[
            t for t in (_text(d) for d in _props(soup, "priorArtKeywords", "dd")) if t
        ],
        prior_art_date=_date(soup, "priorArtDate"),
        citations=_citations(soup, "backwardReferences"),
        family_citations=_citations(soup, "backwardReferencesFamily", family=True),
        cited_by=_citations(soup, "forwardReferences"),
        family_cited_by=_citations(soup, "forwardReferencesFamily", family=True),
        non_patent_citations=[
            t
            for t in (_prop_text(r, "title") for r in _props(soup, "detailedNonPatentLiterature"))
            if t and t != "None"
        ],
        similar_documents=_similar(soup),
        priority_applications=_applications(soup, "priorityApps"),
        applications_claiming_priority=_applications(soup, "appsClaimingPriority"),
        parent_applications=_applications(soup, "parentApps"),
        child_applications=_applications(soup, "childApps"),
        family_applications=_applications(soup, "applications"),
        worldwide_applications=_worldwide(soup),
        also_published_as=_publications(soup),
        country_status=_country_status(soup),
        events=events,
        legal_events=_legal_events(soup),
        landscapes=list(
            dict.fromkeys(
                t for t in (_prop_text(li, "name") for li in _props(soup, "landscapes")) if t
            )
        ),
        links=[
            Link(name=_prop_text(li, "text"), url=a["href"])
            for li in _props(soup, "links", "li")
            for a in [_prop(li, "url", "a")]
            if a is not None and a.get("href")
        ],
    )
