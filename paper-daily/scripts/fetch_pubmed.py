"""PubMed retrieval and normalization through NCBI E-utilities."""

from __future__ import annotations

import os
import time as time_module
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from utils import isoformat_or_empty, normalize_whitespace, requests_get, unique_preserve_order, validate_paper_schema


ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def fetch_pubmed(
    source_config: dict[str, Any],
    research_profile: dict[str, Any],
    target_date: date,
    lookback_days: int,
    logger,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch recent PubMed articles. Network errors are returned as warnings."""

    warnings: list[str] = []
    if not source_config.get("enabled", True):
        return [], warnings

    max_results = int(source_config.get("max_results", 25))
    queries = build_pubmed_queries(source_config, research_profile)
    if not queries:
        warning = "PubMed source is enabled but no search queries could be built."
        logger.warning(warning)
        return [], [warning]

    papers: list[dict[str, Any]] = []
    sleep_seconds = float(source_config.get("sleep_seconds", 0.34))
    for query in queries:
        if len(papers) >= max_results:
            break
        try:
            pmids = search_pubmed(query, source_config, target_date, lookback_days, max_results - len(papers))
            if pmids:
                articles = fetch_pubmed_articles(pmids, source_config)
                papers.extend(normalize_pubmed_article(article) for article in articles)
        except Exception as exc:
            warning = f"PubMed query failed for {query!r}: {exc}"
            warnings.append(warning)
            logger.warning(warning)
        if sleep_seconds > 0:
            time_module.sleep(sleep_seconds)

    deduped = dedupe_by_id(papers)[:max_results]
    logger.info("Fetched %s PubMed articles after date filtering", len(deduped))
    return deduped, warnings


def build_pubmed_queries(source_config: dict[str, Any], research_profile: dict[str, Any]) -> list[str]:
    configured = source_config.get("search_queries")
    if configured:
        if isinstance(configured, str):
            return [configured]
        return unique_preserve_order(configured)

    terms = list(research_profile.get("positive_keywords", []))[:12]
    if not terms:
        terms = list(research_profile.get("background_topics", []))[:12]
    clauses = [f'"{normalize_whitespace(str(term))}"[Title/Abstract]' for term in terms if normalize_whitespace(str(term))]
    return [" OR ".join(clauses)] if clauses else []


def search_pubmed(
    query: str,
    source_config: dict[str, Any],
    target_date: date,
    lookback_days: int,
    max_results: int,
) -> list[str]:
    start_date = target_date - timedelta(days=max(1, int(lookback_days)) - 1)
    params = {
        "db": "pubmed",
        "term": query,
        "mindate": start_date.isoformat(),
        "maxdate": target_date.isoformat(),
        "datetype": str(source_config.get("date_type", "pdat")),
        "retmode": "json",
        "retmax": max(1, max_results),
        "sort": "pub+date",
    }
    add_ncbi_identity_params(params, source_config)
    data = requests_get_json(f"{ESEARCH_URL}?{urlencode(params)}", source_config)
    ids = data.get("esearchresult", {}).get("idlist", []) if isinstance(data, dict) else []
    return [str(pmid) for pmid in ids if str(pmid).strip()]


def fetch_pubmed_articles(pmids: list[str], source_config: dict[str, Any]) -> list[dict[str, Any]]:
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    add_ncbi_identity_params(params, source_config)
    response = requests_get(
        f"{EFETCH_URL}?{urlencode(params)}",
        timeout=int(source_config.get("timeout_seconds", 30)),
    )
    response.raise_for_status()
    return parse_pubmed_xml(response.text)


def requests_get_json(url: str, source_config: dict[str, Any]) -> dict[str, Any]:
    response = requests_get(url, timeout=int(source_config.get("timeout_seconds", 30)))
    response.raise_for_status()
    return response.json()


def add_ncbi_identity_params(params: dict[str, Any], source_config: dict[str, Any]) -> None:
    email = normalize_whitespace(str(source_config.get("email") or os.environ.get("NCBI_EMAIL", "")))
    tool = normalize_whitespace(str(source_config.get("tool") or "paper-daily"))
    api_key_env = normalize_whitespace(str(source_config.get("api_key_env") or "NCBI_API_KEY"))
    api_key = normalize_whitespace(str(source_config.get("api_key") or os.environ.get(api_key_env, "")))
    if email:
        params["email"] = email
    if tool:
        params["tool"] = tool
    if api_key:
        params["api_key"] = api_key


def parse_pubmed_xml(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    articles: list[dict[str, Any]] = []
    for item in root.findall(".//PubmedArticle"):
        pmid = text_of(item.find(".//MedlineCitation/PMID"))
        article = item.find(".//MedlineCitation/Article")
        if article is None or not pmid:
            continue
        doi = ""
        for article_id in item.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if article_id.attrib.get("IdType") == "doi":
                doi = text_of(article_id)
                break
        articles.append(
            {
                "pmid": pmid,
                "title": text_of(article.find("ArticleTitle")),
                "abstract": " ".join(
                    normalize_whitespace("".join(abstract.itertext()))
                    for abstract in article.findall(".//Abstract/AbstractText")
                ),
                "authors": extract_pubmed_authors(article),
                "journal": text_of(article.find(".//Journal/Title")),
                "published_at": pubmed_publication_date(article),
                "doi": doi,
                "mesh_terms": [
                    text_of(heading.find("DescriptorName"))
                    for heading in item.findall(".//MeshHeading")
                    if text_of(heading.find("DescriptorName"))
                ],
            }
        )
    return articles


def normalize_pubmed_article(article: dict[str, Any]) -> dict[str, Any]:
    pmid = normalize_whitespace(str(article.get("pmid") or article.get("id") or ""))
    doi = normalize_whitespace(str(article.get("doi") or ""))
    paper = {
        "id": pmid,
        "source": "pubmed",
        "title": normalize_whitespace(str(article.get("title") or "")),
        "authors": article.get("authors", []),
        "abstract": normalize_whitespace(str(article.get("abstract") or "")),
        "url": PUBMED_URL.format(pmid=pmid) if pmid else (f"https://doi.org/{doi}" if doi else ""),
        "pdf_url": "",
        "published_at": isoformat_or_empty(article.get("published_at")),
        "updated_at": isoformat_or_empty(article.get("updated_at") or article.get("published_at")),
        "venue": normalize_whitespace(str(article.get("journal") or article.get("venue") or "")),
        "categories": article.get("mesh_terms", []) or article.get("categories", []),
        "doi": doi,
    }
    return validate_paper_schema(paper)


def extract_pubmed_authors(article: ET.Element) -> list[str]:
    authors: list[str] = []
    for author in article.findall(".//AuthorList/Author"):
        collective = text_of(author.find("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        last = text_of(author.find("LastName"))
        fore = text_of(author.find("ForeName")) or text_of(author.find("Initials"))
        name = normalize_whitespace(f"{fore} {last}")
        if name:
            authors.append(name)
    return authors


def pubmed_publication_date(article: ET.Element) -> str:
    pub_date = article.find(".//Journal/JournalIssue/PubDate")
    if pub_date is None:
        pub_date = article.find(".//ArticleDate")
    if pub_date is None:
        return ""
    year = text_of(pub_date.find("Year"))
    month = normalize_month(text_of(pub_date.find("Month")) or "1")
    day = text_of(pub_date.find("Day")) or "1"
    if not year:
        return ""
    return f"{year}-{int(month):02d}-{int(day):02d}"


def normalize_month(value: str) -> str:
    months = {
        "jan": "1",
        "feb": "2",
        "mar": "3",
        "apr": "4",
        "may": "5",
        "jun": "6",
        "jul": "7",
        "aug": "8",
        "sep": "9",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    key = value[:3].lower()
    return months.get(key, value if value.isdigit() else "1")


def text_of(element: ET.Element | None) -> str:
    return normalize_whitespace("".join(element.itertext())) if element is not None else ""


def dedupe_by_id(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for paper in papers:
        key = str(paper.get("id") or paper.get("title"))
        if key and key not in seen:
            seen.add(key)
            result.append(paper)
    return result
