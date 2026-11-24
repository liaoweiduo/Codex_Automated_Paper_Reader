#!/usr/bin/env python3
"""Import Zotero Machine Learning collection rows into Obsidian notes.

This is intentionally abstract-only: it does not download PDFs and marks notes
with pdf_backed: false so they do not enter PDF-backed Bases views.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


CANONICAL_CONCEPTS = [
    "concept representation",
    "sparse representation",
    "mechanistic interpretability",
    "disentangled representation",
    "invariant representation",
    "representation drift",
    "continual learning",
    "memory and consolidation",
    "test-time adaptation",
    "out-of-distribution generalization",
    "vision-language model",
    "multimodal learning",
    "latent reasoning",
    "world model",
    "optimization",
    "alignment",
    "multi-objective alignment",
    "evaluation and benchmarking",
    "data attribution",
]

IDEA_THREADS = [
    "Sparse Autoencoder Research Thread",
    "Concept Representation Research Thread",
    "Vision Language Model Research Thread",
    "Latent Reasoning Research Thread",
    "Continual Learning Research Thread",
    "Distribution Shift Research Thread",
    "Multi Objective Alignment Research Thread",
    "Compositional Generalization Research Thread",
    "Diffusion Model Research Thread",
]

TOPIC_RULES = [
    ("sparse representation", ["sparse autoencoder", "sae", "sparse coding", "dictionary learning", "sparsity"]),
    ("mechanistic interpretability", ["mechanistic", "circuit", "causal interpretation", "interpretability", "attribution"]),
    ("concept representation", ["concept", "compositional", "composition", "prototype", "attribute", "representation"]),
    ("continual learning", ["continual", "incremental", "forgetting", "lifelong"]),
    ("test-time adaptation", ["test-time", "adaptation", "online adaptation"]),
    ("out-of-distribution generalization", ["ood", "out-of-distribution", "domain generalization", "distribution shift", "generalization"]),
    ("vision-language model", ["vision-language", "vlm", "clip", "multimodal large language", "visual question answering", "vqa", "image-text"]),
    ("multimodal learning", ["multimodal", "multi-modal", "cross-modal", "vision and language", "visual", "image"]),
    ("evaluation and benchmarking", ["benchmark", "dataset", "evaluation", "challenge", "survey"]),
    ("latent reasoning", ["reasoning", "latent", "working memory", "cognitive"]),
    ("world model", ["world model", "planning", "agent"]),
    ("alignment", ["alignment", "align", "preference"]),
    ("optimization", ["optimization", "training", "finetuning", "fine-tuning", "adapter", "lora"]),
    ("disentangled representation", ["disentangle", "factorized", "factorisation", "factorization"]),
    ("invariant representation", ["invariant", "domain-invariant"]),
    ("representation drift", ["drift", "stability", "stable"]),
]

METHOD_RULES = [
    ("sparse-autoencoder", ["sparse autoencoder", "sae"]),
    ("dictionary-learning", ["dictionary learning", "sparse coding"]),
    ("continual-learning", ["continual learning", "incremental learning", "lifelong learning"]),
    ("adapter", ["adapter", "lora", "parameter-efficient", "peft"]),
    ("vision-language-model", ["vision-language", "vlm", "clip", "multimodal large language"]),
    ("visual-question-answering", ["visual question answering", "vqa"]),
    ("benchmark", ["benchmark", "dataset", "challenge"]),
    ("compositional-generalization", ["compositional", "composition", "compositionality"]),
    ("contrastive-learning", ["contrastive"]),
    ("prototype-learning", ["prototype", "prototypical"]),
    ("masked-modeling", ["masked", "bert pre-training", "mae"]),
    ("object-detection", ["object detection", "detection"]),
    ("segmentation", ["segmentation", "instance segmentation"]),
    ("domain-adaptation", ["domain adaptation", "test-time adaptation", "domain generalization"]),
    ("representation-learning", ["representation learning", "latent representation"]),
    ("mixture-of-experts", ["mixture-of-experts", "moe"]),
    ("reinforcement-learning", ["reinforcement learning", " rl ", " rl."]),
]


def http_json(url: str, timeout: int = 30) -> Any | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CAPR Zotero metadata importer (mailto:liaoweiduo@example.com)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def title_score(a: str, b: str) -> float:
    aa = set(normalize_title(a).split())
    bb = set(normalize_title(b).split())
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def reconstruct_openalex_abstract(inv: dict[str, list[int]] | None) -> str:
    if not inv:
        return ""
    words: list[str] = [""] * (max(pos for poses in inv.values() for pos in poses) + 1)
    for word, positions in inv.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words).strip()


def search_openalex(title: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {
            "search": title,
            "per-page": "5",
            "mailto": "liaoweiduo@example.com",
        }
    )
    data = http_json(f"https://api.openalex.org/works?{query}")
    if not data:
        return None
    best = None
    best_score = 0.0
    for work in data.get("results", []):
        score = title_score(title, work.get("title") or "")
        if score > best_score:
            best = work
            best_score = score
    if not best or best_score < 0.72:
        return None
    authors = [
        a.get("author", {}).get("display_name")
        for a in best.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    ids = best.get("ids") or {}
    primary_location = best.get("primary_location") or {}
    primary_source = primary_location.get("source") or {}
    return {
        "source": "openalex",
        "match_score": best_score,
        "title": best.get("title") or title,
        "authors": authors,
        "year": best.get("publication_year"),
        "published": best.get("publication_date") or str(best.get("publication_year") or ""),
        "venue": primary_source.get("display_name") or "",
        "doi": ids.get("doi", "").replace("https://doi.org/", ""),
        "url": ids.get("doi") or best.get("id") or "",
        "openalex_id": best.get("id") or "",
        "abstract": reconstruct_openalex_abstract(best.get("abstract_inverted_index")),
        "concepts": [c.get("display_name") for c in best.get("concepts", [])[:8] if c.get("display_name")],
    }


def search_semantic_scholar(title: str) -> dict[str, Any] | None:
    fields = "title,abstract,authors,year,venue,publicationDate,externalIds,url,fieldsOfStudy,tldr"
    query = urllib.parse.urlencode({"query": title, "limit": "5", "fields": fields})
    data = http_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{query}")
    if not data:
        return None
    best = None
    best_score = 0.0
    for paper in data.get("data", []):
        score = title_score(title, paper.get("title") or "")
        if score > best_score:
            best = paper
            best_score = score
    if not best or best_score < 0.72:
        return None
    ext = best.get("externalIds") or {}
    url = best.get("url") or ""
    if ext.get("ArXiv"):
        url = f"https://arxiv.org/abs/{ext['ArXiv']}"
    elif ext.get("DOI"):
        url = f"https://doi.org/{ext['DOI']}"
    return {
        "source": "semantic_scholar",
        "match_score": best_score,
        "title": best.get("title") or title,
        "authors": [a.get("name") for a in best.get("authors", []) if a.get("name")],
        "year": best.get("year"),
        "published": best.get("publicationDate") or str(best.get("year") or ""),
        "venue": best.get("venue") or "",
        "doi": ext.get("DOI") or "",
        "arxiv_id": ext.get("ArXiv") or "",
        "url": url,
        "abstract": best.get("abstract") or ((best.get("tldr") or {}).get("text") or ""),
        "fields": best.get("fieldsOfStudy") or [],
    }


def strip_jats(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def crossref_abstract(doi: str) -> str:
    if not doi:
        return ""
    data = http_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")
    if not data:
        return ""
    return strip_jats((data.get("message") or {}).get("abstract") or "")


def search_arxiv(title: str) -> dict[str, Any] | None:
    clean_title = re.sub(r"[:：].*$", "", title).strip() or title
    query = urllib.parse.urlencode(
        {
            "search_query": f'ti:"{clean_title}"',
            "start": "0",
            "max_results": "5",
        }
    )
    req = urllib.request.Request(
        f"https://export.arxiv.org/api/query?{query}",
        headers={"User-Agent": "CAPR Zotero metadata importer (mailto:liaoweiduo@example.com)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return None
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    best = None
    best_score = 0.0
    for entry in root.findall("atom:entry", ns):
        entry_title = re.sub(r"\s+", " ", (entry.findtext("atom:title", default="", namespaces=ns))).strip()
        score = title_score(title, entry_title)
        if score > best_score:
            best = entry
            best_score = score
    if best is None or best_score < 0.70:
        return None
    url = best.findtext("atom:id", default="", namespaces=ns)
    arxiv_id = url.rstrip("/").split("/")[-1]
    authors = [
        a.findtext("atom:name", default="", namespaces=ns)
        for a in best.findall("atom:author", ns)
        if a.findtext("atom:name", default="", namespaces=ns)
    ]
    return {
        "source": "arxiv",
        "match_score": best_score,
        "title": re.sub(r"\s+", " ", best.findtext("atom:title", default=title, namespaces=ns)).strip(),
        "authors": authors,
        "year": (best.findtext("atom:published", default="", namespaces=ns) or "")[:4],
        "published": (best.findtext("atom:published", default="", namespaces=ns) or "")[:10],
        "venue": "arXiv",
        "doi": best.findtext("arxiv:doi", default="", namespaces=ns) or "",
        "arxiv_id": arxiv_id,
        "url": url,
        "abstract": re.sub(r"\s+", " ", best.findtext("atom:summary", default="", namespaces=ns)).strip(),
        "fields": [c.get("term") for c in best.findall("atom:category", ns) if c.get("term")],
    }


def enrich(row: dict[str, str]) -> dict[str, Any]:
    title = row["title"]
    meta = search_openalex(title)
    time.sleep(0.08)
    ss = search_semantic_scholar(title)
    time.sleep(0.08)
    ax = search_arxiv(title)
    time.sleep(0.25)
    if meta and ss:
        if (not meta.get("abstract")) and ss.get("abstract"):
            meta["abstract"] = ss["abstract"]
            meta["abstract_source"] = "semantic_scholar"
        if (not meta.get("authors")) and ss.get("authors"):
            meta["authors"] = ss["authors"]
        if (not meta.get("url")) and ss.get("url"):
            meta["url"] = ss["url"]
        if ss.get("arxiv_id"):
            meta["arxiv_id"] = ss["arxiv_id"]
        if (not meta.get("doi")) and ss.get("doi"):
            meta["doi"] = ss["doi"]
    elif ss:
        meta = ss
    if ax:
        if not meta:
            meta = ax
        else:
            if not meta.get("abstract") and ax.get("abstract"):
                meta["abstract"] = ax["abstract"]
                meta["abstract_source"] = "arxiv"
            if not meta.get("arxiv_id") and ax.get("arxiv_id"):
                meta["arxiv_id"] = ax["arxiv_id"]
            if (not meta.get("url") or "openalex.org" in meta.get("url", "")) and ax.get("url"):
                meta["url"] = ax["url"]
            if (not meta.get("authors")) and ax.get("authors"):
                meta["authors"] = ax["authors"]
            if (not meta.get("published")) and ax.get("published"):
                meta["published"] = ax["published"]
            if not meta.get("venue") and ax.get("venue"):
                meta["venue"] = ax["venue"]
    if not meta:
        meta = {
            "source": "zotero_visible_row",
            "match_score": 0.0,
            "title": title,
            "authors": [row["creator"]] if row.get("creator") else [],
            "published": row.get("date") or "",
            "venue": "",
            "doi": "",
            "url": "",
            "abstract": "",
        }
    if not meta.get("abstract") and meta.get("doi"):
        meta["abstract"] = crossref_abstract(meta.get("doi") or "")
        if meta.get("abstract"):
            meta["abstract_source"] = "crossref"
    meta["zotero_key"] = row.get("key")
    meta["zotero_creator"] = row.get("creator")
    meta["zotero_date"] = row.get("date")
    return meta


def slugify(text: str, max_len: int = 90) -> str:
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.lower()).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].strip("-") or "untitled"


def yaml_string(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "\n" + "\n".join(f"  - {yaml_string(v)}" for v in values)


def infer_topics_methods(meta: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str]]:
    text = " ".join(
        [
            meta.get("title") or "",
            meta.get("abstract") or "",
            " ".join(meta.get("concepts") or []),
            " ".join(meta.get("fields") or []),
        ]
    ).lower()
    topics = [topic for topic, keys in TOPIC_RULES if any(k in text for k in keys)]
    methods = [tag for tag, keys in METHOD_RULES if any(k in text for k in keys)]
    if not topics:
        topics = ["machine learning"]
    if not methods:
        methods = ["paper-summary"]
    concepts = [t for t in topics if t in CANONICAL_CONCEPTS]
    ideas = []
    if "sparse representation" in concepts or "mechanistic interpretability" in concepts:
        ideas.append("Sparse Autoencoder Research Thread")
    if "concept representation" in concepts or "disentangled representation" in concepts or "invariant representation" in concepts:
        ideas.append("Concept Representation Research Thread")
    if "vision-language model" in concepts or "multimodal learning" in concepts:
        ideas.append("Vision Language Model Research Thread")
    if "latent reasoning" in concepts or "world model" in concepts or "memory and consolidation" in concepts:
        ideas.append("Latent Reasoning Research Thread")
    if "continual learning" in concepts or "representation drift" in concepts:
        ideas.append("Continual Learning Research Thread")
    if "out-of-distribution generalization" in concepts or "test-time adaptation" in concepts:
        ideas.append("Distribution Shift Research Thread")
    if "multi-objective alignment" in concepts or "alignment" in concepts:
        ideas.append("Multi Objective Alignment Research Thread")
    if any(k in text for k in ["compositional", "composition", "compositionality"]):
        ideas.append("Compositional Generalization Research Thread")
    ideas = [idea for idea in IDEA_THREADS if idea in set(ideas)]
    return topics[:6], methods[:8], concepts[:6], ideas[:5]


def summarize_from_abstract(meta: dict[str, Any]) -> tuple[str, str, str]:
    abstract = (meta.get("abstract") or "").strip()
    title = meta.get("title") or ""
    if not abstract:
        return (
            "公开元数据未提供 abstract；当前条目只完成 Zotero 可见元数据归档，后续需要手动补摘要。",
            "问题和方法贡献无法从当前公开元数据可靠判断。",
            "todo: 补充 abstract 后重写问题、方法贡献和 concept/idea 链接。",
        )
    sentences = re.split(r"(?<=[.!?])\s+", abstract)
    first = " ".join(sentences[:2]).strip()
    problem = first
    method = " ".join(sentences[2:5]).strip() or first
    one_line = f"基于 abstract：这篇论文关注 {problem}"
    return one_line, problem, method


def existing_paper_notes(vault: Path) -> dict[str, dict[str, Any]]:
    notes: dict[str, dict[str, Any]] = {}
    for path in (vault / "Papers").glob("*/*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm = re.match(r"^---\n(.*?)\n---", text, flags=re.S)
        if not fm:
            continue
        title_match = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', fm.group(1), flags=re.M)
        if not title_match:
            continue
        title = title_match.group(1).strip()
        pdf_backed = bool(re.search(r"^pdf_backed:\s*true\s*$", fm.group(1), flags=re.M))
        status_match = re.search(r'^status:\s*["\']?(.*?)["\']?\s*$', fm.group(1), flags=re.M)
        notes[normalize_title(title)] = {
            "path": path,
            "title": title,
            "pdf_backed": pdf_backed,
            "status": status_match.group(1).strip() if status_match else "",
        }
    return notes


def write_note(meta: dict[str, Any], vault: Path, discovered: str, existing: dict[str, dict[str, Any]]) -> tuple[Path, str]:
    title = meta.get("title") or "Untitled"
    existing_match = existing.get(normalize_title(title))
    if existing_match and existing_match.get("pdf_backed"):
        return existing_match["path"], "reused_pdf_backed"
    published = str(meta.get("published") or meta.get("year") or meta.get("zotero_date") or discovered)
    year_match = re.search(r"\d{4}", published)
    year = year_match.group(0) if year_match else discovered[:4]
    date = published if re.match(r"^\d{4}-\d{2}-\d{2}$", published) else f"{year}-01-01"
    slug = slugify(title)
    out_dir = vault / "Papers" / year
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = existing_match["path"] if existing_match and existing_match.get("status") == "zotero-abstract" else out_dir / f"{date} - {slug}.md"
    topics, methods, concepts, ideas = infer_topics_methods(meta)
    one_line, problem, method = summarize_from_abstract(meta)
    authors = meta.get("authors") or []
    concept_links = ", ".join(f"[[{c}]]" for c in concepts) or "无明确 canonical concept"
    idea_links = ", ".join(f"[[{i}]]" for i in ideas) or "无明确 active idea"
    url = meta.get("url") or ""
    abstract = meta.get("abstract") or ""
    content = f"""---
type: paper
title: {yaml_string(title)}
paper_id: {yaml_string(meta.get("arxiv_id") or meta.get("doi") or meta.get("zotero_key") or slug)}
source: {yaml_string(meta.get("source") or "zotero")}
authors: {yaml_list(authors)}
venue: {yaml_string(meta.get("venue") or "")}
published: {yaml_string(published)}
discovered: {yaml_string(discovered)}
url: {yaml_string(url)}
doi: {yaml_string(meta.get("doi") or "")}
arxiv_id: {yaml_string(meta.get("arxiv_id") or "")}
zotero_key: {yaml_string(meta.get("zotero_key") or "")}
zotero_collection: "Machine Learning"
pdf_backed: false
status: zotero-abstract
reading_evidence: abstract
topics: {yaml_list(topics)}
method_tags: {yaml_list(methods)}
concepts: {yaml_list(concepts)}
ideas: {yaml_list(ideas)}
relevance:
durability:
---
# {date} - {slug}

## 条目 todo list

- [x] 从 Zotero Machine Learning 集合读取可见条目。
- [x] 补齐公开元数据：标题、作者、年份/日期、venue、DOI/arXiv/URL（如果公开 API 可匹配）。
- [x] 不下载 PDF，并明确标记 `pdf_backed: false`、`reading_evidence: abstract`。
- [x] 从 abstract 总结核心问题与方法贡献；abstract 缺失时标记后续补全。
- [x] 维护 `topics`、`method_tags`、`concepts`、`ideas`。

## 一句话总结

{one_line}

## Metadata

- 论文标题：{title}
- 作者：{'; '.join(authors) if authors else meta.get('zotero_creator', '')}
- Published：{published}
- Venue：{meta.get('venue') or ''}
- DOI：{meta.get('doi') or ''}
- arXiv：{meta.get('arxiv_id') or ''}
- URL：{url}
- Zotero key：{meta.get('zotero_key') or ''}
- Metadata source：{meta.get('source') or ''}
- Reading evidence：abstract-only; PDF not downloaded.

## 核心问题

{problem}

## 方法与 contribution

{method}

## Abstract

{abstract if abstract else '公开元数据未提供 abstract。'}

## Topic / Method Tags

- Topics：{', '.join(topics)}
- Method tags：{', '.join(methods)}
- Concepts：{concept_links}
- Ideas：{idea_links}

## Links

- Concepts：{concept_links}
- Ideas：{idea_links}
- Zotero collection：Machine Learning
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path, "written"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows-json", required=True)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows_data = json.loads(Path(args.rows_json).read_text(encoding="utf-8"))
    rows = rows_data["rows"]
    if args.limit:
        rows = rows[: args.limit]
    vault = Path(args.vault)
    discovered = dt.date.today().isoformat()
    enriched = []
    written = []
    existing = existing_paper_notes(vault)
    for idx, row in enumerate(rows, start=1):
        meta = enrich(row)
        note_path, action = write_note(meta, vault, discovered, existing)
        meta["note_path"] = str(note_path)
        meta["note_action"] = action
        enriched.append(meta)
        written.append(str(note_path))
        print(f"[{idx}/{len(rows)}] {action} | {meta.get('source')} | {row['title']}", flush=True)
    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "collection": "Machine Learning",
        "input_count": len(rows),
        "written_count": len(written),
        "new_or_updated_count": sum(1 for item in enriched if item.get("note_action") == "written"),
        "reused_pdf_backed_count": sum(1 for item in enriched if item.get("note_action") == "reused_pdf_backed"),
        "written": written,
        "items": enriched,
    }
    Path(args.out_json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
