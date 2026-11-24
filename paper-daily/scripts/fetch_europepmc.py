"""Europe PMC retrieval and normalization."""

from __future__ import annotations

import time as time_module
from datetime import date, timedelta
from typing import Any

from utils import isoformat_or_empty, normalize_whitespace, requests_get, unique_preserve_order, validate_paper_schema


EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch_europepmc(
    source_config: dict[str, Any],
    research_profile: dict[str, Any],
    target_date: date,
    lookback_days: int,
    logger,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch recent Europe PMC records. Network errors are returned as warnings."""

    warnings: list[str] = []
    if not source_config.get("enabled", True):
        return [], warnings

    max_results = int(source_config.get("max_results", 10))
    queries = build_europepmc_queries(source_config, research_profile)
    if not queries:
        warning = "Europe PMC source is enabled but no search queries could be built."
        logger.warning(warning)
        return [], [warning]

    papers: list[dict[str, Any]] = []
    sleep_seconds = float(source_config.get("sleep_seconds", 0.2))
    for query in queries:
        if len(papers) >= max_results:
            break
        try:
            papers.extend(fetch_europepmc_query(query, source_config, target_date, lookback_days, max_results - len(papers)))
        except Exception as exc:
            warning = f"Europe PMC query failed for {query!r}: {exc}"
            warnings.append(warning)
            logger.warning(warning)
        if sleep_seconds > 0:
            time_module.sleep(sleep_seconds)

    deduped = dedupe_by_id(papers)[:max_results]
    logger.info("Fetched %s Europe PMC records after date filtering", len(deduped))
    return deduped, warnings


def build_europepmc_queries(source_config: dict[str, Any], research_profile: dict[str, Any]) -> list[str]:
    configured = source_config.get("search_queries")
    if configured:
        if isinstance(configured, str):
            return [configured]
        return unique_preserve_order(configured)
    terms = list(research_profile.get("positive_keywords", []))[:6]
    clauses = [f'"{normalize_whitespace(str(term))}"' for term in terms if normalize_whitespace(str(term))]
    return [" OR ".join(clauses)] if clauses else []


def fetch_europepmc_query(
    query: str,
    source_config: dict[str, Any],
    target_date: date,
    lookback_days: int,
    max_results: int,
) -> list[dict[str, Any]]:
    start_date = target_date - timedelta(days=max(1, int(lookback_days)) - 1)
    date_query = f'FIRST_PDATE:[{start_date.isoformat()} TO {target_date.isoformat()}]'
    full_query = f"({query}) AND {date_query}" if query else date_query
    params = {
        "query": full_query,
        "format": "json",
        "pageSize": max(1, max_results),
        "sort": str(source_config.get("sort", "FIRST_PDATE_D desc")),
    }
    response = europepmc_get_with_retries(params, source_config)
    data = response.json()
    results = data.get("resultList", {}).get("result", []) if isinstance(data, dict) else []
    return [normalize_europepmc_result(item) for item in results if item.get("title")]


def europepmc_get_with_retries(params: dict[str, Any], source_config: dict[str, Any]) -> Any:
    retries = int(source_config.get("retries", 1))
    retry_after_seconds = float(source_config.get("retry_after_seconds", 2))
    last_response = None
    for attempt in range(max(1, retries + 1)):
        response = requests_get(
            EUROPEPMC_SEARCH_URL,
            timeout=int(source_config.get("timeout_seconds", 30)),
            params=params,
        )
        last_response = response
        try:
            response.raise_for_status()
            return response
        except Exception:
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code < 500 or attempt >= retries:
                raise
            if retry_after_seconds > 0:
                time_module.sleep(retry_after_seconds)
    assert last_response is not None
    last_response.raise_for_status()
    return last_response


def normalize_europepmc_result(result: dict[str, Any]) -> dict[str, Any]:
    source = normalize_whitespace(str(result.get("source") or ""))
    record_id = normalize_whitespace(str(result.get("id") or result.get("pmid") or result.get("pmcid") or ""))
    doi = normalize_whitespace(str(result.get("doi") or ""))
    paper = {
        "id": f"{source}:{record_id}" if source and record_id else record_id,
        "source": "europepmc",
        "title": normalize_whitespace(str(result.get("title") or "")),
        "authors": split_authors(result.get("authorString")),
        "abstract": normalize_whitespace(str(result.get("abstractText") or "")),
        "url": europepmc_url(result, source, record_id, doi),
        "pdf_url": normalize_whitespace(str(result.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url", "")))
        if isinstance(result.get("fullTextUrlList"), dict)
        else "",
        "published_at": isoformat_or_empty(result.get("firstPublicationDate") or result.get("firstIndexDate")),
        "updated_at": isoformat_or_empty(result.get("firstIndexDate") or result.get("firstPublicationDate")),
        "venue": normalize_whitespace(str(result.get("journalTitle") or "")),
        "categories": extract_keywords(result),
        "doi": doi,
    }
    return validate_paper_schema(paper)


def europepmc_url(result: dict[str, Any], source: str, record_id: str, doi: str) -> str:
    if result.get("pmcid"):
        return f"https://europepmc.org/article/PMC/{result['pmcid']}"
    if source and record_id:
        return f"https://europepmc.org/article/{source}/{record_id}"
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def split_authors(author_string: Any) -> list[str]:
    return [normalize_whitespace(author) for author in str(author_string or "").split(",") if normalize_whitespace(author)]


def extract_keywords(result: dict[str, Any]) -> list[str]:
    keyword_list = result.get("keywordList")
    if isinstance(keyword_list, dict):
        keywords = keyword_list.get("keyword", [])
        if isinstance(keywords, str):
            keywords = [keywords]
        return unique_preserve_order(keywords)
    return []


def dedupe_by_id(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for paper in papers:
        key = str(paper.get("id") or paper.get("title"))
        if key and key not in seen:
            seen.add(key)
            result.append(paper)
    return result
