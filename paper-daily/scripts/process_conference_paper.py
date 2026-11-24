"""Process one pending conference paper and checkpoint Obsidian progress."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from conference_papers import render_conference_markdown
from utils import write_json_atomic
from openreview_auth import DEFAULT_TOKEN_FILE as DEFAULT_OPENREVIEW_TOKEN_FILE, openreview_access_token


CONCEPT_BY_KEYWORD = {
    "sparse autoencoder": "sparse representation",
    "concept representation": "concept representation",
    "compositional representation": "compositionality",
    "disentangled representation": "disentangled representation",
    "invariant representation": "invariant representation",
    "continual learning": "continual learning",
    "test-time adaptation": "test-time adaptation",
    "out-of-distribution": "out-of-distribution generalization",
    "domain generalization": "out-of-distribution generalization",
    "vision-language model": "vision-language model",
    "multimodal alignment": "multimodal learning",
    "cross-modal representation learning": "multimodal learning",
    "alignment": "alignment",
    "diffusion model": "diffusion models",
    "evaluation": "evaluation and benchmarking",
    "benchmark": "evaluation and benchmarking",
}

IDEA_BY_KEYWORD = {
    "sparse autoencoder": "Sparse Autoencoder Research Thread",
    "concept representation": "Concept Representation Research Thread",
    "compositional representation": "Compositional Generalization Research Thread",
    "continual learning": "Continual Learning Research Thread",
    "test-time adaptation": "Distribution Shift Research Thread",
    "out-of-distribution": "Distribution Shift Research Thread",
    "vision-language model": "Vision Language Model Research Thread",
    "multimodal alignment": "Multi Objective Alignment Research Thread",
    "alignment": "Multi Objective Alignment Research Thread",
    "diffusion model": "Diffusion Model Research Thread",
}

def select_next_pending_paper(
    payload: dict[str, Any], retry_failed: bool = True, excluded_ids: set[str] | None = None
) -> dict[str, Any] | None:
    for paper in payload.get("papers", []):
        if str(paper.get("id")) in (excluded_ids or set()):
            continue
        if paper.get("status") == "completed":
            continue
        if retry_failed or paper.get("status") in {"pending", "processing"}:
            return paper
    return None


def _yaml_scalar(value: Any) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def _safe_unicode(value: str) -> str:
    """Drop malformed UTF-16 surrogate code points from extracted PDF text."""
    return str(value or "").encode("utf-8", "replace").decode("utf-8")


def _title_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def find_arxiv_pdf_url(title: str) -> str | None:
    """Return an arXiv PDF only when the title match is unambiguously strong."""
    if not title:
        return None
    # arXiv's title search rejects long exact-title phrases containing
    # punctuation/model names. ANDing three distinctive title tokens keeps the
    # query narrow while allowing the strict full-title check below.
    stopwords = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    tokens = [re.sub(r"[^A-Za-z0-9]", "", word) for word in str(title).split()]
    tokens = [word for word in tokens if len(word) >= 4 and word.lower() not in stopwords][:3]
    if not tokens:
        return None
    query = quote(" AND ".join(f"all:{word}" for word in tokens))
    request = Request(
        f"https://export.arxiv.org/api/query?search_query={query}&max_results=50",
        headers={"User-Agent": "CAPR conference paper processor/0.1"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            root = ElementTree.fromstring(response.read())
    except Exception:
        return None
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    target = _title_key(title)
    best: tuple[float, str] | None = None
    for entry in root.findall("atom:entry", namespace):
        candidate = " ".join((entry.findtext("atom:title", "", namespace) or "").split())
        similarity = difflib.SequenceMatcher(None, target, _title_key(candidate)).ratio()
        identifier = (entry.findtext("atom:id", "", namespace) or "").strip()
        if identifier and similarity >= 0.94 and (best is None or similarity > best[0]):
            best = (similarity, identifier)
    if best is None:
        return None
    return best[1].replace("http://arxiv.org/abs/", "https://arxiv.org/pdf/").replace(
        "https://arxiv.org/abs/", "https://arxiv.org/pdf/"
    )


def openreview_attachment_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "openreview.net" not in parsed.netloc:
        return None
    paper_id = parse_qs(parsed.query).get("id", [""])[0]
    if not paper_id:
        return None
    return f"https://api2.openreview.net/attachment?id={quote(paper_id)}&name=pdf"


def render_paper_note(paper: dict[str, Any], concept_links: list[str], idea_links: list[str]) -> str:
    authors = json.dumps(paper.get("authors", []), ensure_ascii=False)
    topics = json.dumps(paper.get("matched_keywords", []), ensure_ascii=False)
    concepts = ", ".join(concept_links) if concept_links else "待后续映射"
    ideas = ", ".join(idea_links) if idea_links else "待后续映射"
    title = paper.get("title", "Untitled paper")
    return f"""---
type: paper
title: {_yaml_scalar(title)}
paper_id: {_yaml_scalar(paper.get('id'))}
source: {_yaml_scalar(paper.get('source'))}
authors: {authors}
venue: {_yaml_scalar(paper.get('venue'))}
published: {_yaml_scalar(paper.get('published_at'))}
discovered: {_yaml_scalar(date.today().isoformat())}
url: {_yaml_scalar(paper.get('url'))}
pdf_source_url: {_yaml_scalar(paper.get('pdf_source_url') or paper.get('pdf_url'))}
pdf_backed: true
pdf_text_source: {_yaml_scalar(paper.get('pdf_text_path'))}
pdf_file_source: {_yaml_scalar(paper.get('pdf_path'))}
source_evidence: "PDF downloaded and text extracted by conference paper processor"
reading_evidence: pdf
daily_report: {_yaml_scalar('2026-icml-papers')}
status: conference-queue-completed
topics: {topics}
method_tags: []
relevance: {_yaml_scalar('keyword-matched conference candidate; verify from PDF')}
durability: {_yaml_scalar('pending deep reading')}
---

# {title}

## 一句话总结

待基于 PDF 深读补充；当前摘要：{paper.get('abstract') or '无摘要'}

## Source Evidence / PDF Metadata

- PDF 文件：`{paper.get('pdf_path', '')}`
- PDF 文本：`{paper.get('pdf_text_path', '')}`
- 论文页面：{paper.get('url', '')}
- PDF 链接：{paper.get('pdf_source_url') or paper.get('pdf_url', '')}
- 证据等级：PDF 已下载并抽取文本；下方分析必须基于实际 PDF 阅读。

## 针对的问题

待阅读 PDF 后补充。

## 核心架构与训练方法

待阅读 PDF 后补充。

## 关键实验与结论

待阅读 PDF 后补充。

## Claim 是否被实验支撑

待阅读 PDF 后补充；不要只依据摘要下结论。

## 总结：与其他相似工作的区别

待阅读 PDF 后补充；需要与对应 Concept 的现有方法轴和相邻论文比较。

## 和我的研究的关系

- 关注关键词：{', '.join(paper.get('matched_keywords', [])) or '无'}
- Concepts：{concepts}
- Ideas：{ideas}

## 局限与风险

待阅读 PDF 后补充。

## 可迁移 idea

待阅读 PDF 后补充。先保留为候选，不把摘要中的 claim 当作已验证结论。

## Links

- Concepts: {concepts}
- Ideas: {ideas}
- Paper page: {paper.get('url', '')}
- PDF: {paper.get('pdf_source_url') or paper.get('pdf_url', '')}

## 原始摘要

{paper.get('abstract') or '无摘要'}
"""


def _append_unique_page_entry(path: Path, section: str, entry: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = f"## {section}"
    if entry in text:
        return
    if marker not in text:
        text = text.rstrip() + f"\n\n{marker}\n"
    text = text.rstrip() + f"\n- {entry}\n"
    path.write_text(text, encoding="utf-8")


def _append_related_paper_frontmatter(path: Path, note_link: str) -> None:
    """Maintain the canonical idea-page related_papers list idempotently."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "related_papers:":
            continue
        insert_at = index + 1
        while insert_at < len(lines) and lines[insert_at].lstrip().startswith("-"):
            if note_link in lines[insert_at]:
                return
            insert_at += 1
        lines.insert(insert_at, f"- '{note_link}'")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return
    for index, line in enumerate(lines):
        if line.strip() == "---" and index > 0:
            lines.insert(index, "related_papers:\n- '" + note_link + "'")
            path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            return


def add_paper_to_knowledge_pages(
    vault_root: Path, paper: dict[str, Any], concept_names: list[str], idea_names: list[str]
) -> None:
    note_link = paper.get("note_link", "")
    title = paper.get("title", paper.get("id", "paper"))
    evidence_label = "PDF-backed" if paper.get("pdf_backed") else "conference queue; verify from PDF"
    entry = f"{note_link} — {title} ({evidence_label})"
    for concept_name in concept_names:
        path = vault_root / "Concepts" / f"{concept_name}.md"
        if path.exists():
            _append_unique_page_entry(path, "Conference Paper Queue — ICML 2026", entry)
    for idea_name in idea_names:
        path = vault_root / "Ideas" / f"{idea_name}.md"
        if path.exists():
            _append_unique_page_entry(path, "Conference Paper Queue — ICML 2026", entry)
            _append_related_paper_frontmatter(path, note_link)


def _links_for_paper(vault_root: Path, paper: dict[str, Any]) -> tuple[list[str], list[str]]:
    concepts: list[str] = []
    ideas: list[str] = []
    for keyword in paper.get("matched_keywords", []):
        key = str(keyword).lower()
        concept = CONCEPT_BY_KEYWORD.get(key)
        if concept and (vault_root / "Concepts" / f"{concept}.md").exists():
            concepts.append(f"[[{concept}]]")
        idea = IDEA_BY_KEYWORD.get(key)
        if idea and (vault_root / "Ideas" / f"{idea}.md").exists():
            ideas.append(f"[[{idea}]]")
    return list(dict.fromkeys(concepts)), list(dict.fromkeys(ideas))


def download_pdf(url: str, destination: Path, title: str = "") -> str:
    if not url:
        raise RuntimeError("No PDF URL is available for this paper")
    destination.parent.mkdir(parents=True, exist_ok=True)
    token = openreview_access_token()
    api_attachment = openreview_attachment_url(url) if token else None
    arxiv_url = find_arxiv_pdf_url(title) if "openreview.net" in url else None
    # Prefer a public preprint when there is an unambiguous title match; this
    # avoids consuming OpenReview attachment quota unnecessarily.
    if os.environ.get("OPENREVIEW_ARXIV_ONLY") == "1":
        candidates = [arxiv_url] if arxiv_url else []
    else:
        candidates = [candidate for candidate in [arxiv_url, api_attachment, url] if candidate]
    if not candidates:
        if os.environ.get("OPENREVIEW_ARXIV_ONLY") == "1":
            raise RuntimeError("No strictly matched arXiv PDF was found")
        raise RuntimeError("No usable PDF candidate was found")
    errors: list[str] = []
    rate_limit_exhausted = False
    for candidate in candidates:
        token = openreview_access_token()
        headers = {
            "User-Agent": "CAPR conference paper processor/0.1",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
        }
        if token and "openreview.net" in candidate:
            headers["Cookie"] = f"openreview.accessToken={token}"
            headers["Authorization"] = f"Bearer {token}"
        with tempfile.NamedTemporaryFile(prefix=f".{destination.name}.", dir=destination.parent, delete=False) as tmp:
            temp_path = Path(tmp.name)
            try:
                request = Request(candidate, headers=headers)
                retry_delay = max(1.0, float(os.environ.get("OPENREVIEW_RETRY_DELAY", "60")))
                long_retry_delay = max(
                    retry_delay,
                    float(os.environ.get("OPENREVIEW_LONG_RETRY_DELAY", "1200")),
                )
                long_retry_after = max(1, int(os.environ.get("OPENREVIEW_LONG_RETRY_AFTER", "3")))
                max_attempts = max(1, int(os.environ.get("OPENREVIEW_MAX_ATTEMPTS", "10")))
                for attempt in range(max_attempts):
                    try:
                        with urlopen(request, timeout=90) as response:
                            content_type = str(response.headers.get("Content-Type", "")).lower()
                            if "text/html" in content_type:
                                raise RuntimeError(f"PDF endpoint returned HTML instead of PDF: {candidate}")
                            shutil.copyfileobj(response, tmp)
                        break
                    except Exception as exc:
                        status = getattr(exc, "code", None)
                        if status != 429 or attempt == max_attempts - 1:
                            if status == 429:
                                rate_limit_exhausted = True
                            raise
                        # OpenReview may advertise a much longer Retry-After.
                        # The conference workflow deliberately retries gently
                        # at a fixed one-minute cadence, so a transient 429
                        # does not abort the paper-processing checkpoint.
                        delay = long_retry_delay if attempt + 1 >= long_retry_after else retry_delay
                        print(
                            f"[rate-limit] retrying this paper in {delay:.0f}s "
                            f"({attempt + 1}/{max_attempts})",
                            file=sys.stderr,
                            flush=True,
                        )
                        time.sleep(delay)
                if "openreview.net" in candidate:
                    time.sleep(float(os.environ.get("OPENREVIEW_REQUEST_DELAY", "1.0")))
                os.replace(temp_path, destination)
                return candidate
            except Exception as exc:
                temp_path.unlink(missing_ok=True)
                errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
                if rate_limit_exhausted:
                    break
    raise RuntimeError("; ".join(errors))


def extract_pdf_text(pdf_path: Path, text_path: Path) -> None:
    text_path.parent.mkdir(parents=True, exist_ok=True)
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        subprocess.run([pdftotext, "-layout", str(pdf_path), str(text_path)], check=True, timeout=120)
    else:
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                import pdfplumber
            except ImportError as exc:
                raise RuntimeError("PDF extraction requires pdftotext, pypdf, or pdfplumber") from exc
            with pdfplumber.open(pdf_path) as pdf:
                extracted = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
                text_path.write_text(_safe_unicode(extracted), encoding="utf-8")
        else:
            reader = PdfReader(str(pdf_path))
            extracted = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            text_path.write_text(_safe_unicode(extracted), encoding="utf-8")
    if not text_path.read_text(encoding="utf-8").strip():
        raise RuntimeError(f"PDF text extraction returned empty text: {pdf_path}")


def process_one(
    queue_path: Path,
    vault_root: Path,
    retry_failed: bool = True,
    excluded_ids: set[str] | None = None,
) -> dict[str, Any]:
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    paper = select_next_pending_paper(payload, retry_failed=retry_failed, excluded_ids=excluded_ids)
    if paper is None:
        return {"status": "complete", "message": "No pending papers remain"}
    note_filename = paper["note_filename"]
    stem = note_filename[:-3] if note_filename.endswith(".md") else note_filename
    pdf_path = vault_root / "Attachments" / "Paper PDFs" / f"{stem}.pdf"
    text_path = vault_root / "_paper_text" / f"{stem}.txt"
    year = int(payload.get("year", 2026) or 2026)
    note_path = vault_root / "Papers" / str(year) / note_filename
    try:
        paper["status"] = "processing"
        paper["pdf_path"] = str(pdf_path)
        paper["pdf_text_path"] = str(text_path)
        paper["pdf_source_url"] = download_pdf(
            str(paper.get("pdf_url", "")), pdf_path, str(paper.get("title", ""))
        )
        extract_pdf_text(pdf_path, text_path)
        paper["reading_evidence"] = "pdf"
        paper["pdf_backed"] = True
        concept_links, idea_links = _links_for_paper(vault_root, paper)
        paper["note_link"] = f"[[Papers/2026/{stem}]]"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(render_paper_note(paper, concept_links, idea_links), encoding="utf-8")
        add_paper_to_knowledge_pages(
            vault_root,
            paper,
            [link[2:-2] for link in concept_links],
            [link[2:-2] for link in idea_links],
        )
        paper["status"] = "completed"
        paper.pop("failure_reason", None)
        paper["completed_at"] = date.today().isoformat()
        result = {"status": "completed", "paper_id": paper["id"], "note_path": str(note_path)}
    except Exception as exc:
        paper["status"] = "failed"
        paper["failure_reason"] = f"{type(exc).__name__}: {exc}"
        result = {"status": "failed", "paper_id": paper["id"], "error": paper["failure_reason"]}
    paper_by_id = {str(item.get("id")): item for item in payload.get("papers", [])}
    for direction_papers in payload.get("directions", {}).values():
        for direction_paper in direction_papers:
            source = paper_by_id.get(str(direction_paper.get("id")))
            if source:
                direction_paper.update(source)
    write_json_atomic(queue_path, payload)
    rendered_queue = render_conference_markdown(payload)
    (queue_path.parent / "conference-review.md").write_text(rendered_queue, encoding="utf-8")
    conference_slug = re.sub(r"[^a-z0-9]+", "-", str(payload.get("conference", "conference")).lower()).strip("-")
    obsidian_queue = vault_root / "Research Notes" / f"{year}-{conference_slug}-papers.md"
    obsidian_queue.parent.mkdir(parents=True, exist_ok=True)
    obsidian_queue.write_text(rendered_queue, encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending conference papers one by one.")
    parser.add_argument("--queue", default="data/conferences/icml-2026/papers.json")
    parser.add_argument("--obsidian-root", default=None)
    parser.add_argument("--count", type=int, default=1, help="Number of papers to process; default is one")
    parser.add_argument(
        "--skip-failed",
        action="store_true",
        help="Keep failed papers unchecked but continue to later pending papers",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Retry failed papers and continue after individual failures",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queue_path = Path(args.queue).resolve()
    root_value = args.obsidian_root or os.environ.get("OBSIDIAN_KNOWLEDGE_ROOT", "")
    if not root_value:
        raise SystemExit("--obsidian-root or OBSIDIAN_KNOWLEDGE_ROOT is required")
    failed_this_run: set[str] = set()
    for _ in range(max(1, args.count)):
        result = process_one(
            queue_path,
            Path(root_value).expanduser(),
            retry_failed=not args.skip_failed or args.continue_on_failure,
            excluded_ids=failed_this_run if args.continue_on_failure else None,
        )
        print(json.dumps(result, ensure_ascii=False))
        if result.get("status") == "failed" and result.get("paper_id"):
            failed_this_run.add(str(result["paper_id"]))
        if result.get("status") != "completed" and not (args.skip_failed or args.continue_on_failure):
            break


if __name__ == "__main__":
    main()
