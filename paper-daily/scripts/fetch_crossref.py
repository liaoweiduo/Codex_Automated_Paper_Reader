"""Crossref retrieval and normalization."""

from __future__ import annotations

import re
import time as time_module
from datetime import date, timedelta
from typing import Any

from utils import isoformat_or_empty, normalize_whitespace, requests_get, unique_preserve_order, validate_paper_schema


CROSSREF_WORKS_URL = "https://api.crossref.org/works"


def fetch_crossref(
    source_config: dict[str, Any],
    research_profile: dict[str, Any],
    target_date: date,
    lookback_days: int,
    logger,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch recent Crossref works. Network errors are returned as warnings."""

    warnings: list[str] = []
    if not source_config.get("enabled", True):
        return [], warnings

    max_results = int(source_config.get("max_results", 20))
    searches = build_crossref_searches(source_config, research_profile)
    if not searches:
        warning = "Crossref source is enabled but no search queries or ISSNs are configured."
        logger.warning(warning)
        return [], [warning]

    papers: list[dict[str, Any]] = []
    sleep_seconds = float(source_config.get("sleep_seconds", 0.2))
    for search in searches:
        if len(papers) >= max_results:
            break
        try:
            papers.extend(fetch_crossref_search(search, source_config, target_date, lookback_days, max_results - len(papers)))
        except Exception as exc:
            warning = f"Crossref search failed for {search!r}: {exc}"
            warnings.append(warning)
            logger.warning(warning)
        if sleep_seconds > 0:
            time_module.sleep(sleep_seconds)

    deduped = dedupe_by_id(papers)[:max_results]
    logger.info("Fetched %s Crossref works after date filtering", len(deduped))
    return deduped, warnings


def build_crossref_searches(source_config: dict[str, Any], research_profile: dict[str, Any]) -> list[dict[str, str]]:
    searches: list[dict[str, str]] = []
    for issn in source_config.get("issns", []) or []:
        if normalize_whitespace(str(issn)):
            searches.append({"issn": normalize_whitespace(str(issn))})
    configured = source_config.get("search_queries") or []
    if isinstance(configured, str):
        configured = [configured]
    for query in configured:
        if normalize_whitespace(str(query)):
            searches.append({"query": normalize_whitespace(str(query))})
    if not searches:
        for journal in source_config.get("target_journals", []) or research_profile.get("target_journals", []) or []:
            if normalize_whitespace(str(journal)):
                searches.append({"container_title": normalize_whitespace(str(journal))})
    return searches


def fetch_crossref_search(
    search: dict[str, str],
    source_config: dict[str, Any],
    target_date: date,
    lookback_days: int,
    max_results: int,
) -> list[dict[str, Any]]:
    start_date = target_date - timedelta(days=max(1, int(lookback_days)) - 1)
    filters = [
        f"from-pub-date:{start_date.isoformat()}",
        f"until-pub-date:{target_date.isoformat()}",
        f"type:{source_config.get('type', 'journal-article')}",
    ]
    if search.get("issn"):
        filters.append(f"issn:{search['issn']}")

    params: dict[str, Any] = {
        "filter": ",".join(filters),
        "rows": max(1, max_results),
        "sort": str(source_config.get("sort", "published")),
        "order": str(source_config.get("order", "desc")),
    }
    if search.get("query"):
        params["query.bibliographic"] = search["query"]
    if search.get("container_title"):
        params["query.container-title"] = search["container_title"]
    mailto = normalize_whitespace(str(source_config.get("mailto") or ""))
    if mailto:
        params["mailto"] = mailto

    response = requests_get(CROSSREF_WORKS_URL, timeout=int(source_config.get("timeout_seconds", 30)), params=params)
    response.raise_for_status()
    data = response.json()
    items = data.get("message", {}).get("items", []) if isinstance(data, dict) else []
    return [normalize_crossref_work(item) for item in items if item.get("title")]


def normalize_crossref_work(work: dict[str, Any]) -> dict[str, Any]:
    doi = normalize_whitespace(str(work.get("DOI") or ""))
    title = first_list_value(work.get("title"))
    abstract = strip_markup(first_list_value([work.get("abstract", "")]))
    categories = unique_preserve_order(list(work.get("subject", []) or []) + list(work.get("ISSN", []) or []))
    paper = {
        "id": doi or normalize_whitespace(str(work.get("URL") or title)),
        "source": "crossref",
        "title": title,
        "authors": extract_crossref_authors(work),
        "abstract": abstract,
        "url": normalize_whitespace(str(work.get("URL") or (f"https://doi.org/{doi}" if doi else ""))),
        "pdf_url": first_crossref_pdf(work),
        "published_at": isoformat_or_empty(crossref_date(work)),
        "updated_at": isoformat_or_empty(work.get("indexed", {}).get("date-time") or crossref_date(work)),
        "venue": first_list_value(work.get("container-title")),
        "categories": categories,
        "doi": doi,
    }
    return validate_paper_schema(paper)


def extract_crossref_authors(work: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for item in work.get("author", []) or []:
        given = normalize_whitespace(str(item.get("given") or ""))
        family = normalize_whitespace(str(item.get("family") or ""))
        name = normalize_whitespace(f"{given} {family}") or normalize_whitespace(str(item.get("name") or ""))
        if name:
            authors.append(name)
    return authors


def crossref_date(work: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "created", "deposited"):
        date_parts = work.get(key, {}).get("date-parts") if isinstance(work.get(key), dict) else None
        if date_parts and date_parts[0]:
            parts = list(date_parts[0])
            while len(parts) < 3:
                parts.append(1)
            return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return ""


def first_list_value(value: Any) -> str:
    if isinstance(value, list):
        return normalize_whitespace(str(value[0])) if value else ""
    return normalize_whitespace(str(value or ""))


def first_crossref_pdf(work: dict[str, Any]) -> str:
    for link in work.get("link", []) or []:
        if "pdf" in str(link.get("content-type", "")).lower() and link.get("URL"):
            return normalize_whitespace(str(link.get("URL")))
    return ""


def strip_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return normalize_whitespace(text)


def dedupe_by_id(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for paper in papers:
        key = str(paper.get("id") or paper.get("title"))
        if key and key not in seen:
            seen.add(key)
            result.append(paper)
    return result
