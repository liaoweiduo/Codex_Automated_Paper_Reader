"""Semantic Scholar enrichment for already-discovered papers.

This module deliberately does not search for new papers. It only annotates
records that were retrieved by deterministic source APIs.
"""

from __future__ import annotations

import os
import time as time_module
from typing import Any

from utils import normalize_whitespace, requests_get


S2_GRAPH_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
S2_FIELDS = "citationCount,influentialCitationCount,isOpenAccess,openAccessPdf"


def enrich_semantic_scholar(
    papers: list[dict[str, Any]],
    source_config: dict[str, Any],
    logger,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Annotate existing papers with Semantic Scholar metadata when available."""

    warnings: list[str] = []
    if not source_config.get("enabled", True):
        return papers, warnings

    max_results = min(len(papers), int(source_config.get("max_results", len(papers))))
    api_key_env = normalize_whitespace(str(source_config.get("api_key_env") or "SEMANTIC_SCHOLAR_API_KEY"))
    api_key = normalize_whitespace(str(source_config.get("api_key") or os.environ.get(api_key_env, "")))
    headers = {"x-api-key": api_key} if api_key else None
    sleep_seconds = float(source_config.get("sleep_seconds", 1.0 if not api_key else 0.1))
    timeout = int(source_config.get("timeout_seconds", 20))

    enriched: list[dict[str, Any]] = []
    for idx, paper in enumerate(papers):
        if idx >= max_results:
            enriched.append(paper)
            continue
        identifier = semantic_scholar_identifier(paper)
        if not identifier:
            enriched.append(paper)
            continue
        try:
            response = requests_get(
                S2_GRAPH_PAPER_URL.format(paper_id=identifier),
                timeout=timeout,
                headers=headers,
                params={"fields": S2_FIELDS},
            )
            if response.status_code == 404:
                enriched.append(paper)
                continue
            response.raise_for_status()
            enriched.append(merge_s2_metadata(paper, response.json()))
        except Exception as exc:
            warnings.append(f"Semantic Scholar enrichment failed for {identifier}: {exc}")
            enriched.append(paper)
        if sleep_seconds > 0:
            time_module.sleep(sleep_seconds)

    if len(enriched) < len(papers):
        enriched.extend(papers[len(enriched) :])
    logger.info("Semantic Scholar enrichment attempted for %s papers", min(max_results, len(papers)))
    return enriched, warnings


def semantic_scholar_identifier(paper: dict[str, Any]) -> str:
    doi = normalize_whitespace(str(paper.get("doi") or ""))
    if doi:
        return f"DOI:{doi}"
    source = normalize_whitespace(str(paper.get("source") or "")).lower()
    paper_id = normalize_whitespace(str(paper.get("id") or ""))
    if source == "arxiv" and paper_id:
        return f"ARXIV:{paper_id}"
    if source == "pubmed" and paper_id:
        return f"PMID:{paper_id}"
    return ""


def merge_s2_metadata(paper: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(paper)
    merged["semantic_scholar_id"] = normalize_whitespace(str(data.get("paperId") or ""))
    merged["semantic_scholar_url"] = normalize_whitespace(str(data.get("url") or ""))
    merged["citation_count"] = int(data.get("citationCount") or 0)
    merged["influential_citation_count"] = int(data.get("influentialCitationCount") or 0)
    open_pdf = data.get("openAccessPdf") if isinstance(data.get("openAccessPdf"), dict) else {}
    if not merged.get("pdf_url") and open_pdf.get("url"):
        merged["pdf_url"] = normalize_whitespace(str(open_pdf.get("url")))
    return merged
