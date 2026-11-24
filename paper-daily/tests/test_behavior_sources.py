import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from daily_papers import resolve_enabled_sources, run_pipeline
from fetch_crossref import normalize_crossref_work
from fetch_europepmc import normalize_europepmc_result
from fetch_europepmc import fetch_europepmc_query
from fetch_osf_psyarxiv import normalize_osf_preprint
from fetch_osf_psyarxiv import fetch_psyarxiv_query
from fetch_pubmed import normalize_pubmed_article


def test_pubmed_article_normalizes_to_candidate_schema():
    article = {
        "pmid": "12345",
        "title": "Habit formation and reward learning",
        "abstract": "A behavioral study of habit formation.",
        "authors": ["Jane Doe", "Alan Smith"],
        "journal": "Journal of Behavioral Decision Making",
        "published_at": "2026-06-22",
        "doi": "10.1234/example",
        "mesh_terms": ["Habits", "Decision Making"],
    }

    paper = normalize_pubmed_article(article)

    assert paper["id"] == "12345"
    assert paper["source"] == "pubmed"
    assert paper["title"] == "Habit formation and reward learning"
    assert paper["authors"] == ["Jane Doe", "Alan Smith"]
    assert paper["venue"] == "Journal of Behavioral Decision Making"
    assert paper["categories"] == ["Habits", "Decision Making"]
    assert paper["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert paper["pdf_url"] == ""


def test_osf_psyarxiv_preprint_normalizes_to_candidate_schema():
    item = {
        "id": "abcde",
        "attributes": {
            "title": "Risk perception in social decision making",
            "description": "A PsyArXiv preprint.",
            "date_published": "2026-06-22T09:00:00Z",
            "date_modified": "2026-06-22T10:00:00Z",
        },
        "links": {"html": "https://osf.io/preprints/psyarxiv/abcde"},
    }

    paper = normalize_osf_preprint(item)

    assert paper["id"] == "abcde"
    assert paper["source"] == "psyarxiv"
    assert paper["title"] == "Risk perception in social decision making"
    assert paper["venue"] == "PsyArXiv"
    assert paper["url"] == "https://osf.io/preprints/psyarxiv/abcde"


def test_psyarxiv_query_filters_terms_locally(monkeypatch):
    captured_params = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "id": "abcde",
                        "attributes": {
                            "title": "Risk perception in social decision making",
                            "description": "A PsyArXiv preprint.",
                            "date_published": "2026-06-22T09:00:00Z",
                        },
                        "links": {"html": "https://osf.io/preprints/psyarxiv/abcde"},
                    },
                    {
                        "id": "zzzzz",
                        "attributes": {
                            "title": "Unrelated memory paper",
                            "description": "",
                            "date_published": "2026-06-22T09:00:00Z",
                        },
                        "links": {"html": "https://osf.io/preprints/psyarxiv/zzzzz"},
                    },
                ]
            }

    def fake_get(url, timeout=30, params=None):
        captured_params.update(params or {})
        return Response()

    monkeypatch.setattr("fetch_osf_psyarxiv.requests_get", fake_get)

    papers = fetch_psyarxiv_query("risk perception", {"provider": "psyarxiv"}, date(2026, 6, 22), 1, 10)

    assert "filter[q]" not in captured_params
    assert captured_params["filter[provider]"] == "psyarxiv"
    assert [paper["id"] for paper in papers] == ["abcde"]


def test_crossref_work_normalizes_to_candidate_schema():
    work = {
        "DOI": "10.5555/example",
        "title": ["Emotion regulation and choice behavior"],
        "abstract": "<jats:p>Behavioral evidence.</jats:p>",
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "container-title": ["Cognition"],
        "published-print": {"date-parts": [[2026, 6, 22]]},
        "URL": "https://doi.org/10.5555/example",
        "ISSN": ["0010-0277"],
        "subject": ["Psychology"],
    }

    paper = normalize_crossref_work(work)

    assert paper["id"] == "10.5555/example"
    assert paper["source"] == "crossref"
    assert paper["title"] == "Emotion regulation and choice behavior"
    assert paper["abstract"] == "Behavioral evidence."
    assert paper["authors"] == ["Ada Lovelace"]
    assert paper["venue"] == "Cognition"
    assert paper["categories"] == ["Psychology", "0010-0277"]


def test_europepmc_result_normalizes_to_candidate_schema():
    result = {
        "id": "98765",
        "source": "MED",
        "title": "Cognitive control in human behavior",
        "abstractText": "A study of cognitive control.",
        "authorString": "Doe J, Smith A",
        "journalTitle": "Psychological Science",
        "firstPublicationDate": "2026-06-22",
        "doi": "10.7777/example",
        "pmid": "98765",
        "keywordList": {"keyword": ["Cognitive Control"]},
    }

    paper = normalize_europepmc_result(result)

    assert paper["id"] == "MED:98765"
    assert paper["source"] == "europepmc"
    assert paper["title"] == "Cognitive control in human behavior"
    assert paper["authors"] == ["Doe J", "Smith A"]
    assert paper["venue"] == "Psychological Science"
    assert paper["categories"] == ["Cognitive Control"]


def test_europepmc_retries_transient_server_errors(monkeypatch):
    calls = {"count": 0}

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 500:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "id": "98765",
                            "source": "MED",
                            "title": "Cognitive control in human behavior",
                            "firstPublicationDate": "2026-06-22",
                        }
                    ]
                }
            }

    def fake_get(url, timeout=30, params=None):
        calls["count"] += 1
        return Response(503 if calls["count"] == 1 else 200)

    monkeypatch.setattr("fetch_europepmc.requests_get", fake_get)
    monkeypatch.setattr("fetch_europepmc.time_module.sleep", lambda seconds: None)

    papers = fetch_europepmc_query(
        "cognitive control",
        {"retries": 1, "retry_after_seconds": 0},
        date(2026, 6, 22),
        1,
        10,
    )

    assert calls["count"] == 2
    assert papers[0]["source"] == "europepmc"


def test_behavior_sources_are_supported_by_daily_pipeline():
    config = {
        "sources": {
            "arxiv": {"enabled": False},
            "pubmed": {"enabled": True},
            "psyarxiv": {"enabled": True},
            "crossref": {"enabled": True},
            "europepmc": {"enabled": True},
            "semantic_scholar": {"enabled": True},
        }
    }
    args = argparse.Namespace(sources=None)

    assert resolve_enabled_sources(args, config) == [
        "pubmed",
        "psyarxiv",
        "crossref",
        "europepmc",
        "semantic_scholar",
    ]


def test_daily_pipeline_uses_behavior_source_fetchers(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
research_profile:
  positive_keywords:
    - habit formation
  negative_keywords: []
sources:
  arxiv:
    enabled: false
  openreview:
    enabled: false
  pubmed:
    enabled: true
    max_results: 25
  psyarxiv:
    enabled: true
    max_results: 15
  crossref:
    enabled: true
    max_results: 20
  europepmc:
    enabled: true
    max_results: 10
  semantic_scholar:
    enabled: true
    max_results: 30
output:
  report_dir: reports
  data_dir: data
  log_dir: logs
retrieval:
  candidate_limit: 100
""",
        encoding="utf-8",
    )

    def fake_source(name):
        def _fetch(*args):
            return [
                {
                    "id": f"{name}-1",
                    "source": name,
                    "title": f"{name} habit formation",
                    "authors": [],
                    "abstract": "habit formation",
                    "url": "",
                    "pdf_url": "",
                    "published_at": "2026-06-22T00:00:00+00:00",
                    "updated_at": "2026-06-22T00:00:00+00:00",
                    "venue": "",
                    "categories": [],
                }
            ], []

        return _fetch

    monkeypatch.setattr("daily_papers.run_network_preflight", lambda *args: None)
    monkeypatch.setattr("daily_papers.fetch_pubmed", fake_source("pubmed"))
    monkeypatch.setattr("daily_papers.fetch_psyarxiv", fake_source("psyarxiv"))
    monkeypatch.setattr("daily_papers.fetch_crossref", fake_source("crossref"))
    monkeypatch.setattr("daily_papers.fetch_europepmc", fake_source("europepmc"))
    def fake_enrich(papers, *args):
        enriched = []
        for paper in papers:
            copy = dict(paper)
            copy["citation_count"] = 42
            copy["semantic_scholar_id"] = "s2-paper"
            enriched.append(copy)
        return enriched, []

    monkeypatch.setattr("daily_papers.enrich_semantic_scholar", fake_enrich)

    args = argparse.Namespace(
        config=str(config_path),
        date="2026-06-22",
        stage="fetch",
        lookback_days=None,
        force=True,
        sources=None,
    )
    result = run_pipeline(args)

    assert result["source_counts"] == {
        "pubmed": 1,
        "psyarxiv": 1,
        "crossref": 1,
        "europepmc": 1,
        "semantic_scholar": 4,
    }
    candidates = json.loads(Path(result["candidates_path"]).read_text(encoding="utf-8"))
    assert {paper["source"] for paper in candidates} == {"pubmed", "psyarxiv", "crossref", "europepmc"}
    assert all(paper["citation_count"] == 42 for paper in candidates)
    assert all(paper["semantic_scholar_id"] == "s2-paper" for paper in candidates)


def test_behavior_config_keeps_daily_candidate_pool_at_100():
    import yaml

    config_path = Path(__file__).resolve().parents[1] / "config.behavior.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["retrieval"]["candidate_limit"] == 100
    enabled_sources = {
        name: source
        for name, source in config["sources"].items()
        if source.get("enabled", True) and name != "semantic_scholar"
    }
    assert sum(int(source.get("max_results", 0)) for source in enabled_sources.values()) == 100
