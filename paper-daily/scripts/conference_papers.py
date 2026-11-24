"""Manually fetch and summarize a released conference paper collection."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from urllib.parse import parse_qs, urlparse
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from fetch_openreview import fetch_openreview_venue
from rank_papers import score_candidate_rules
from utils import dedupe_papers, ensure_dirs, load_config, write_json_atomic


DEFAULT_OBSIDIAN_ROOT = Path(
    "/Users/liaoweiduo/Library/CloudStorage/OneDrive-Personal/Researchs/obsidian sync/knowledge"
)

DEFAULT_DIRECTION_RULES = {
    "Representation and Compositionality": [
        "representation learning",
        "compositional representation",
        "disentangled representation",
        "sparse autoencoder",
    ],
    "Multimodal and VLM": [
        "vision-language model",
        "multimodal",
        "cross-modal",
        "multimodal alignment",
    ],
    "Adaptation and Continual Learning": [
        "test-time adaptation",
        "online adaptation",
        "continual learning",
        "domain adaptation",
        "distribution shift",
    ],
    "Alignment and Preference": [
        "alignment",
        "preference optimization",
        "reinforcement learning from human feedback",
        "reward model",
    ],
    "Generative Models": ["diffusion model", "generative model", "flow matching", "language model"],
    "Theory and Optimization": ["optimization", "generalization", "convergence", "theory"],
    "Evaluation and Safety": ["evaluation", "benchmark", "robustness", "safety", "interpretability"],
}


def official_virtual_urls(conference: str, year: int) -> tuple[str, str] | None:
    """Return official conference-page JSON endpoints when a known adapter exists."""

    if conference.strip().lower() == "icml" and year == 2026:
        base = "https://icml.cc/static/virtual/data"
        return f"{base}/icml-2026-orals-posters.json", f"{base}/icml-2026-abstracts.json"
    return None


def _load_json_url(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "paper-conference-ingest/0.1", "Accept": "application/json"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def normalize_virtual_paper(
    item: dict[str, Any],
    abstracts: dict[str, Any],
    conference: str,
    year: int,
    source_url: str,
) -> dict[str, Any]:
    """Normalize an official conference virtual-site record to the paper schema."""

    paper_id = str(item.get("id", "")).strip()
    authors = [
        str(author.get("fullname", "")).strip()
        for author in item.get("authors", [])
        if isinstance(author, dict) and str(author.get("fullname", "")).strip()
    ]
    virtual_url = str(item.get("virtualsite_url", "") or "")
    if virtual_url.startswith("/"):
        virtual_url = f"https://icml.cc{virtual_url}"
    paper_url = item.get("paper_url") or ""
    if not paper_url:
        for media in item.get("eventmedia", []) or []:
            if not isinstance(media, dict):
                continue
            candidate = str(media.get("uri", "") or "").strip()
            if "openreview.net/forum?id=" in candidate:
                paper_url = candidate
                break
    paper_url = paper_url or virtual_url
    pdf_url = item.get("paper_pdf_url") or ""
    if not pdf_url and paper_url:
        paper_id_from_url = parse_qs(urlparse(str(paper_url)).query).get("id", [""])[0]
        if paper_id_from_url and "openreview.net/forum" in str(paper_url):
            pdf_url = f"https://openreview.net/pdf?id={paper_id_from_url}"
    categories = [item.get("topic", ""), *item.get("keywords", [])]
    return {
        "id": paper_id,
        "source": "icml_virtual",
        "title": item.get("name", ""),
        "authors": authors,
        "abstract": abstracts.get(paper_id, ""),
        "url": paper_url,
        "pdf_url": pdf_url,
        "published_at": "",
        "updated_at": "",
        "venue": f"{conference} {year}",
        "categories": [str(value) for value in categories if value],
        "conference_source_url": source_url,
        "decision": item.get("decision", ""),
        "virtual_url": virtual_url,
    }


def fetch_virtual_conference(
    main_url: str, abstracts_url: str, conference: str, year: int, max_results: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch and normalize a conference's official virtual-site JSON export."""

    main_payload = _load_json_url(main_url)
    abstract_payload = _load_json_url(abstracts_url) if abstracts_url else {}
    items = main_payload.get("results", []) if isinstance(main_payload, dict) else main_payload
    if not isinstance(items, list):
        raise ValueError(f"Conference JSON does not contain a results list: {main_url}")
    abstracts = abstract_payload if isinstance(abstract_payload, dict) else {}
    papers = [normalize_virtual_paper(item, abstracts, conference, year, main_url) for item in items[:max_results]]
    warnings = []
    if len(papers) < len(items):
        warnings.append(f"Official conference source truncated at max_results={max_results}")
    missing_abstracts = sum(1 for paper in papers if not paper.get("abstract"))
    if missing_abstracts:
        warnings.append(f"{missing_abstracts} papers have no abstract in the official export")
    return papers, warnings


def candidate_invitations(conference: str, year: int, explicit: str | None = None) -> list[str]:
    """Return explicit and conventional OpenReview invitations in priority order."""

    from fetch_openreview import candidate_venue_ids

    values = [explicit] if explicit else []
    values.extend(candidate_venue_ids(conference, year))
    return list(dict.fromkeys(str(value) for value in values if value))


def assign_direction(
    paper: dict[str, Any], profile: dict[str, Any], direction_rules: dict[str, list[str]] | None = None
) -> str:
    """Assign a stable, human-readable direction using profile vocabulary."""

    text = " ".join(
        [str(paper.get("title", "")), str(paper.get("abstract", "")), *map(str, paper.get("categories", []))]
    ).lower()
    for direction, keywords in (direction_rules or {}).items():
        if any(str(keyword).strip().lower() in text for keyword in keywords if str(keyword).strip()):
            return str(direction)
    for keyword in profile.get("positive_keywords", []):
        label = str(keyword).strip()
        if label and label.lower() in text:
            return label
    categories = paper.get("categories", [])
    if categories:
        return str(categories[0])
    return "Other"


def paper_note_filename(paper: dict[str, Any], conference: str, year: int) -> str:
    """Return a stable, Obsidian-safe paper note filename."""

    title = unicodedata.normalize("NFKC", str(paper.get("title", "paper"))).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", title).strip("-")[:90].strip("-") or str(paper.get("id", "paper"))
    conference_slug = re.sub(r"[^a-z0-9]+", "-", conference.lower()).strip("-")
    return f"{year}-{conference_slug}-{slug}.md"


def build_payload(
    papers: list[dict[str, Any]],
    conference: str,
    year: int,
    venue_id: str,
    profile: dict[str, Any],
    direction_rules: dict[str, list[str]] | None = None,
    candidate_limit: int = 100,
) -> dict[str, Any]:
    scored = []
    for paper in papers:
        annotated = score_candidate_rules(paper, profile, date(year, 12, 31))
        annotated["direction"] = assign_direction(annotated, profile, direction_rules)
        scored.append(annotated)
    matched = [paper for paper in scored if paper.get("matched_keywords")]
    matched.sort(
        key=lambda item: (
            float(item.get("keyword_score", 0)),
            float(item.get("coarse_retrieval_score", 0)),
            item.get("published_at", ""),
        ),
        reverse=True,
    )
    keyword_matched_count = len(matched)
    scored = matched[: max(0, int(candidate_limit))]
    directions: dict[str, list[dict[str, Any]]] = {}
    for paper in scored:
        directions.setdefault(paper["direction"], []).append(paper)
    return {
        "conference": conference,
        "year": year,
        "venue_id": venue_id,
        "retrieved_count": len(papers),
        "keyword_matched_count": keyword_matched_count,
        "candidate_limit": int(candidate_limit),
        "paper_count": len(scored),
        "warnings": [],
        "directions": directions,
        "papers": scored,
    }


def _heading(value: str) -> str:
    return str(value).strip().title() or "Other"


def _inline(value: Any) -> str:
    return str(value or "").replace("\n", " ").strip()


def render_conference_markdown(payload: dict[str, Any]) -> str:
    conference = _inline(payload.get("conference"))
    year = _inline(payload.get("year"))
    lines = [
        f"# {conference} {year} Papers",
        "",
        f"> Generated conference collection: `{conference} {year}`",
        f"> Venue: `{_inline(payload.get('venue_id'))}`",
        f"> Paper count: **{payload.get('paper_count', 0)}**",
        "",
        "## Directions",
        "",
    ]
    lines.extend(["## Processing Queue", "", "按排序后的顺序逐篇处理。完成 PDF 下载、文本抽取和 Obsidian paper note 后，才将对应项目改为 `[x]`。", ""])
    queue_papers = payload.get("papers") or [
        paper for direction_papers in payload.get("directions", {}).values() for paper in direction_papers
    ]
    for paper in queue_papers:
        checkbox = "x" if paper.get("status") == "completed" else " "
        note_filename = paper.get("note_filename") or paper_note_filename(
            paper, str(payload.get("conference", "conference")), int(payload.get("year", 0) or 0)
        )
        note_stem = note_filename[:-3] if note_filename.endswith(".md") else note_filename
        title = _inline(paper.get("title")) or str(paper.get("id", "paper"))
        lines.append(f"- [{checkbox}] [[Papers/2026/{note_stem}|{title}]] — `{paper.get('id', '')}`")
    lines.extend(["", "## Direction Index", ""])
    for direction, papers in payload.get("directions", {}).items():
        anchor = re.sub(r"[^a-z0-9 -]", "", str(direction).lower()).replace(" ", "-")
        lines.append(f"- [{_heading(direction)}](#{anchor}) — {len(papers)} papers")
    for direction, papers in payload.get("directions", {}).items():
        lines.extend(["", f"## {_heading(direction)}", ""])
        for index, paper in enumerate(papers, 1):
            title = _inline(paper.get("title")) or "Untitled paper"
            lines.extend(
                [
                    f"### {index}. [{title}]({_inline(paper.get('url'))})",
                    "",
                    f"- Authors: {_inline('; '.join(paper.get('authors', [])))}",
                    f"- Paper ID: `{_inline(paper.get('id'))}`",
                    f"- Venue: {_inline(paper.get('venue'))}",
                    f"- Published: {_inline(paper.get('published_at'))}",
                    f"- PDF: {_inline(paper.get('pdf_url'))}",
                    f"- Decision: {_inline(paper.get('decision')) or 'Not provided'}",
                    f"- Virtual page: {_inline(paper.get('virtual_url')) or 'Not provided'}",
                    f"- Direction: {_inline(paper.get('direction'))}",
                    f"- Retrieval score: {_inline(paper.get('coarse_retrieval_score'))}",
                    "",
                    f"**Abstract:** {_inline(paper.get('abstract')) or 'No abstract provided.'}",
                    "",
                ]
            )
    if payload.get("warnings"):
        lines.extend(["## Retrieval warnings", "", *[f"- {_inline(item)}" for item in payload["warnings"]], ""])
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch a released conference paper collection.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--conference", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--invitation", default=None)
    parser.add_argument("--source-url", default=None, help="Official conference JSON export URL")
    parser.add_argument("--abstracts-url", default=None, help="Matching abstract JSON export URL")
    parser.add_argument("--max-results", type=int, default=None)
    parser.add_argument("--candidate-limit", type=int, default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--obsidian-root", default=None)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, str | int]:
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    conference_slug = re.sub(r"[^a-z0-9]+", "-", args.conference.lower()).strip("-")
    output_dir = Path(args.output_dir).resolve() if args.output_dir else config_path.parent / "data" / "conferences" / f"{conference_slug}-{args.year}"
    ensure_dirs([output_dir])
    json_path = output_dir / "papers.json"
    markdown_path = output_dir / "conference-review.md"
    if json_path.exists() and markdown_path.exists() and not args.force:
        return {"json_path": str(json_path), "markdown_path": str(markdown_path), "paper_count": 0, "skipped": 1}

    conference_config = config.get("conference", {})
    max_results = args.max_results or int(conference_config.get("max_results", 50000))
    candidate_limit = getattr(args, "candidate_limit", None) or int(conference_config.get("candidate_limit", 500))
    virtual_urls = official_virtual_urls(args.conference, args.year)
    source_url = getattr(args, "source_url", None) or (
        virtual_urls[0] if virtual_urls and not getattr(args, "invitation", None) else ""
    )
    abstracts_url = getattr(args, "abstracts_url", None) or (
        virtual_urls[1] if virtual_urls and source_url else ""
    )
    if source_url:
        papers, warnings = fetch_virtual_conference(
            source_url, abstracts_url, args.conference, args.year, max_results
        )
        venue_id = source_url
    else:
        source_config = config.get("sources", {}).get("openreview", {})
        papers, warnings, venue_id = fetch_openreview_venue(
            source_config,
            args.conference,
            args.year,
            explicit_invitation=args.invitation,
            max_results=max_results,
        )
    if not papers and warnings:
        raise RuntimeError("Conference fetch failed: " + "; ".join(warnings))
    direction_rules = config.get("conference", {}).get("directions") or DEFAULT_DIRECTION_RULES
    payload = build_payload(
        papers,
        args.conference,
        args.year,
        venue_id,
        config.get("research_profile", {}),
        direction_rules,
        candidate_limit=candidate_limit,
    )
    previous_by_id: dict[str, dict[str, Any]] = {}
    if json_path.exists():
        try:
            previous = json.loads(json_path.read_text(encoding="utf-8"))
            previous_by_id = {str(item.get("id")): item for item in previous.get("papers", [])}
        except (OSError, ValueError, TypeError):
            previous_by_id = {}
    for paper in payload["papers"]:
        previous_paper = previous_by_id.get(str(paper.get("id")), {})
        paper["status"] = previous_paper.get("status", "pending")
        paper["note_filename"] = previous_paper.get("note_filename") or paper_note_filename(
            paper, args.conference, args.year
        )
        paper["note_link"] = f"[[Papers/2026/{paper['note_filename'][:-3]}]]"
    payload["warnings"] = warnings
    if not payload["papers"]:
        raise RuntimeError("No conference papers matched the configured positive_keywords")
    write_json_atomic(json_path, payload)
    markdown = render_conference_markdown(payload)
    markdown_path.write_text(markdown, encoding="utf-8")

    obsidian_root = Path(args.obsidian_root).expanduser() if args.obsidian_root else Path(
        os.environ.get("OBSIDIAN_KNOWLEDGE_ROOT", str(DEFAULT_OBSIDIAN_ROOT))
    )
    obsidian_path = obsidian_root / "Research Notes" / f"{args.year}-{conference_slug}-papers.md"
    ensure_dirs([obsidian_path])
    obsidian_path.write_text(markdown, encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "obsidian_path": str(obsidian_path),
        "paper_count": payload["paper_count"],
        "skipped": 0,
    }


def main() -> None:
    try:
        result = run(parse_args())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
