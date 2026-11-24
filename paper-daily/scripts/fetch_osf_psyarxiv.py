"""PsyArXiv retrieval and normalization through OSF preprints."""

from __future__ import annotations

import time as time_module
from datetime import date, timedelta
from typing import Any

from utils import isoformat_or_empty, normalize_whitespace, parse_datetime, requests_get, unique_preserve_order, validate_paper_schema


OSF_PREPRINTS_URL = "https://api.osf.io/v2/preprints/"


def fetch_psyarxiv(
    source_config: dict[str, Any],
    research_profile: dict[str, Any],
    target_date: date,
    lookback_days: int,
    logger,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch recent PsyArXiv preprints. Network errors are returned as warnings."""

    warnings: list[str] = []
    if not source_config.get("enabled", True):
        return [], warnings

    max_results = int(source_config.get("max_results", 15))
    queries = build_psyarxiv_queries(source_config, research_profile)
    if not queries:
        queries = [""]

    papers: list[dict[str, Any]] = []
    sleep_seconds = float(source_config.get("sleep_seconds", 0.2))
    for query in queries:
        if len(papers) >= max_results:
            break
        try:
            papers.extend(fetch_psyarxiv_query(query, source_config, target_date, lookback_days, max_results - len(papers)))
        except Exception as exc:
            warning = f"PsyArXiv query failed for {query!r}: {exc}"
            warnings.append(warning)
            logger.warning(warning)
        if sleep_seconds > 0:
            time_module.sleep(sleep_seconds)

    deduped = dedupe_by_id(papers)[:max_results]
    logger.info("Fetched %s PsyArXiv preprints after date filtering", len(deduped))
    return deduped, warnings


def build_psyarxiv_queries(source_config: dict[str, Any], research_profile: dict[str, Any]) -> list[str]:
    configured = source_config.get("search_queries")
    if configured:
        if isinstance(configured, str):
            return [configured]
        return unique_preserve_order(configured)
    return unique_preserve_order(list(research_profile.get("positive_keywords", []))[:5])


def fetch_psyarxiv_query(
    query: str,
    source_config: dict[str, Any],
    target_date: date,
    lookback_days: int,
    max_results: int,
) -> list[dict[str, Any]]:
    start_date = target_date - timedelta(days=max(1, int(lookback_days)) - 1)
    params: dict[str, Any] = {
        "filter[provider]": source_config.get("provider", "psyarxiv"),
        "page[size]": min(max(1, int(source_config.get("page_size", 50))), 100),
        "sort": str(source_config.get("sort", "-date_modified")),
    }

    response = requests_get(OSF_PREPRINTS_URL, timeout=int(source_config.get("timeout_seconds", 30)), params=params)
    response.raise_for_status()
    data = response.json()
    papers: list[dict[str, Any]] = []
    for item in data.get("data", []):
        paper = normalize_osf_preprint(item)
        dt = parse_datetime(paper.get("published_at")) or parse_datetime(paper.get("updated_at"))
        if dt and not (start_date <= dt.date() <= target_date):
            continue
        if query and not paper_matches_query(paper, query):
            continue
        papers.append(paper)
        if len(papers) >= max_results:
            break
    return papers


def normalize_osf_preprint(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes", {}) if isinstance(item.get("attributes"), dict) else {}
    links = item.get("links", {}) if isinstance(item.get("links"), dict) else {}
    preprint_id = normalize_whitespace(str(item.get("id") or ""))
    published = attrs.get("date_published") or attrs.get("date_created")
    updated = attrs.get("date_modified") or published
    paper = {
        "id": preprint_id,
        "source": "psyarxiv",
        "title": normalize_whitespace(str(attrs.get("title") or "")),
        "authors": [],
        "abstract": normalize_whitespace(str(attrs.get("description") or "")),
        "url": normalize_whitespace(str(links.get("html") or f"https://osf.io/preprints/psyarxiv/{preprint_id}")),
        "pdf_url": normalize_whitespace(str(links.get("download") or "")),
        "published_at": isoformat_or_empty(published),
        "updated_at": isoformat_or_empty(updated),
        "venue": "PsyArXiv",
        "categories": ["preprint", "psychology"],
    }
    return validate_paper_schema(paper)


def paper_matches_query(paper: dict[str, Any], query: str) -> bool:
    haystack = " ".join(
        [
            str(paper.get("title", "")),
            str(paper.get("abstract", "")),
            " ".join(paper.get("categories", [])),
        ]
    ).lower()
    terms = [term for term in normalize_whitespace(query).lower().split() if term]
    return all(term in haystack for term in terms)


def dedupe_by_id(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for paper in papers:
        key = str(paper.get("id") or paper.get("title"))
        if key and key not in seen:
            seen.add(key)
            result.append(paper)
    return result
