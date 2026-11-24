#!/usr/bin/env python3
"""Import Consensus MER related-work CSV rows into the Obsidian vault."""

from __future__ import annotations

import csv
import html
import re
import textwrap
from pathlib import Path


CSV_PATH = Path(
    "/Users/liaoweiduo/Downloads/情绪识别多模态任务的基础模型研究相关工作 - Jun 11, 2026.csv"
)
VAULT = Path(
    "/Users/liaoweiduo/Library/CloudStorage/OneDrive-Personal/Researchs/obsidian sync/knowledge"
)
PAPERS_DIR = VAULT / "Papers"
RESEARCH_NOTES_DIR = VAULT / "Research Notes"
BASES_DIR = VAULT / "Bases"
CONCEPT_PATH = VAULT / "Concepts" / "multimodal learning.md"

DISCOVERED = "2026-06-11"
COLLECTION = "multimodal-emotion-recognition-foundation-models"
SOURCE_NOTE_NAME = "Multimodal Emotion Recognition Related Work - 2026-06-11"
SOURCE_NOTE_WIKILINK = f"[[{SOURCE_NOTE_NAME}]]"
MER_CONCEPT = "emotion recognition"


def slugify(text: str, max_len: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_len].strip("-") or "untitled"


def q(value: object) -> str:
    text = "" if value is None else html.unescape(str(value))
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "\n" + "\n".join(f"  - {q(v)}" for v in values)


def authors(raw: str) -> list[str]:
    return [html.unescape(part.strip()) for part in raw.split(",") if part.strip()]


def arxiv_id_from_doi(doi: str) -> str:
    match = re.match(r"10\.48550/arxiv\.(.+)", doi.strip(), re.I)
    return match.group(1) if match else ""


def infer_topics(row: dict[str, str]) -> list[str]:
    text = " ".join([row.get("Title", ""), row.get("Abstract", ""), row.get("Takeaway", "")]).lower()
    topics = ["multimodal learning"]
    if "affective" in text or "emotion" in text:
        topics.append("affective computing")
    if "sentiment" in text:
        topics.append("sentiment analysis")
    if any(k in text for k in ["large language", "llm", "multimodal large language", "affectgpt", "emoverse"]):
        topics.append("vision-language model")
    if any(k in text for k in ["physiological", "eeg", "ecg", "eda"]):
        topics.append("physiological signals")
    if "cross-subject" in text or "domain" in text or "generaliz" in text:
        topics.append("out-of-distribution generalization")
    return list(dict.fromkeys(topics))


def infer_tags(row: dict[str, str]) -> list[str]:
    text = " ".join([row.get("Title", ""), row.get("Abstract", ""), row.get("Takeaway", "")]).lower()
    tags = ["multimodal-emotion-recognition"]
    if "survey" in text or "review" in text:
        tags.append("survey")
    if "deep learning" in text:
        tags.append("deep-learning")
    if "fusion" in text:
        tags.append("multimodal-fusion")
    if "attention" in text:
        tags.append("attention-fusion")
    if "transformer" in text:
        tags.append("transformer-fusion")
    if "large language" in text or "llm" in text or "mllm" in text:
        tags.append("large-language-model")
    if "pretrain" in text or "pre-trained" in text or "pretrained" in text:
        tags.append("pretrained-model")
    if "prompt" in text:
        tags.append("prompt-engineering")
    if "physiological" in text or "eeg" in text or "ecg" in text or "eda" in text:
        tags.append("physiological-signal")
    if "conversation" in text or "dialogue" in text or "multi-party" in text:
        tags.append("conversation-emotion-recognition")
    if "dataset" in text or "benchmark" in text:
        tags.append("benchmark-dataset")
    if "ensemble" in text:
        tags.append("ensemble")
    if "graph neural" in text or "gnn" in text:
        tags.append("graph-neural-network")
    if "contrastive" in text:
        tags.append("contrastive-learning")
    return list(dict.fromkeys(tags))


def paper_note(row: dict[str, str]) -> tuple[Path, str, str]:
    title = html.unescape(row["Title"].strip())
    doi = row.get("DOI", "").strip()
    year = row.get("Year", "").strip() or "unknown"
    published = f"{year}-01-01" if year.isdigit() else ""
    paper_id = doi or slugify(title)
    arxiv_id = arxiv_id_from_doi(doi)
    url = f"https://doi.org/{doi}" if doi else row.get("Consensus Link", "").strip()
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""
    study_type = row.get("Study Type", "").strip()
    venue = html.unescape(row.get("Journal", "").strip())
    citations = row.get("Citations", "").strip()
    quartile = row.get("Journal SJR Quartile", "").strip()
    note_slug = slugify(title)
    path = PAPERS_DIR / year / f"{published or DISCOVERED} - {note_slug}.md"
    abstract = html.unescape(row.get("Abstract", "").strip())
    takeaway = html.unescape(row.get("Takeaway", "").strip())
    tags = infer_tags(row)
    topics = infer_topics(row)
    concepts = [MER_CONCEPT]
    concepts.extend(topic for topic in topics if (VAULT / "Concepts" / f"{topic}.md").exists())
    concepts = list(dict.fromkeys(concepts))

    summary = takeaway or abstract[:240].strip()
    problem = (
        "这篇条目被导入为多模态情绪识别相关工作的候选文献，主要服务于整理 MER / affective "
        "computing 中的模型、数据集、融合策略和 benchmark 脉络。"
    )
    method = (
        "当前 note 基于 Consensus CSV 元数据生成，尚未做 PDF-backed 深读；方法细节需以后续 PDF 或原文为准。"
    )
    if study_type:
        method += f" 该条目的研究类型标记为 {study_type}。"
    evidence = "证据来自 Consensus 导出的标题、takeaway、摘要、DOI、venue 与引用数；未下载 PDF，也未抽取全文。"
    relation = (
        "可作为情绪识别多模态任务基础模型 related work 的检索入口，尤其用于梳理 "
        "text/audio/vision/physiological signals 的融合路线。"
    )
    body = f"""---
type: paper
title: {q(title)}
paper_id: {q(paper_id)}
source: "consensus_related_work"
authors: {yaml_list(authors(row.get("Authors", "")))}
venue: {q(venue)}
published: {q(published)}
discovered: {q(DISCOVERED)}
url: {q(url)}
doi: {q(doi)}
arxiv_id: {q(arxiv_id)}
pdf_url: {q(pdf_url)}
pdf_backed: false
status: related-work-candidate
reading_evidence: consensus-export
related_work_collection: {q(COLLECTION)}
related_work_source: {q(SOURCE_NOTE_WIKILINK)}
study_type: {q(study_type)}
citations: {int(citations) if citations.isdigit() else q(citations)}
journal_sjr_quartile: {q(quartile)}
consensus_url: {q(row.get("Consensus Link", "").strip())}
topics: {yaml_list(topics)}
method_tags: {yaml_list(tags)}
concepts: {yaml_list(concepts)}
ideas:
  - "Vision Language Model Research Thread"
relevance:
durability:
---
# {published or DISCOVERED} - {note_slug}

## 条目 todo list

- [x] 从 Consensus CSV 导入相关工作元数据。
- [x] 标记为 `pdf_backed: false`、`reading_evidence: consensus-export`，避免进入 PDF-backed 主库。
- [ ] 后续如要进入主 Paper Library，需要下载 PDF、抽取全文，并基于 PDF text 重写核心方法/实验/局限。

## 一句话总结

{summary or "Consensus CSV 未提供 takeaway 或摘要，需要后续补全。"}

## Metadata

- 论文标题：{title}
- 作者：{'; '.join(authors(row.get("Authors", "")))}
- Published：{published}
- Venue：{venue}
- DOI：{doi}
- arXiv：{arxiv_id}
- Citations：{citations}
- Journal SJR Quartile：{quartile}
- Consensus：{row.get("Consensus Link", "").strip()}
- Related-work collection：{COLLECTION}
- Reading evidence：Consensus CSV metadata; PDF not downloaded.

## 核心问题

{problem}

## 方法与 contribution

{method}

## Abstract

{abstract or "Consensus CSV 未提供 abstract。"}

## 实验证据

{evidence}

## Claim 是否被实验支撑

未判断。当前条目不是 PDF-backed 深读，只能说明它是 related-work 候选，不能据此评价 claim 是否被完整实验支撑。

## 和我的研究的关系

{relation}

## 局限与风险

- 该 note 暂时不是长期主库论文条目；缺少 PDF text、实验细节和作者原文表述。
- Consensus takeaway 可能压缩或改写论文贡献，正式引用前应回到 DOI/arXiv/PDF。

## Topic / Method Tags

- Topics：{', '.join(topics)}
- Method tags：{', '.join(tags)}
- Concepts：{', '.join(f"[[{c}]]" for c in concepts)}
- Ideas：[[Vision Language Model Research Thread]]

## Links

{chr(10).join(f"- Concepts：[[{c}]]" for c in concepts) if concepts else "- Concepts：待后续映射"}
- Ideas：[[Vision Language Model Research Thread]]
- Source index：{SOURCE_NOTE_WIKILINK}
"""
    return path, body, f"[[{published or DISCOVERED} - {note_slug}]]"


def source_note(rows: list[dict[str, str]], links: list[str]) -> str:
    table_rows = []
    for row, link in zip(rows, links):
        title = html.unescape(row["Title"].strip()).replace("|", "\\|")
        table_rows.append(
            "| "
            + " | ".join(
                [
                    link,
                    row.get("Year", "").strip(),
                    row.get("Study Type", "").strip() or "-",
                    html.unescape(row.get("Journal", "").strip()) or "-",
                    row.get("Citations", "").strip() or "-",
                    row.get("DOI", "").strip() or "-",
                    title,
                ]
            )
            + " |"
        )
    return f"""---
type: research_note
title: "{SOURCE_NOTE_NAME}"
created: {DISCOVERED}
source: "consensus_csv"
related_work_collection: "{COLLECTION}"
paper_count: {len(rows)}
topics:
  - "multimodal learning"
  - "affective computing"
method_tags:
  - "multimodal-emotion-recognition"
---
# {SOURCE_NOTE_NAME}

## Summary

这批条目来自 Consensus CSV，用于整理“情绪识别多模态任务的基础模型研究”相关工作。当前导入目标是形成 Obsidian 可筛选的 related-work database：所有 paper notes 均标记为 `pdf_backed: false` 与 `status: related-work-candidate`，因此不会进入严格 PDF-backed 的主 `Paper Library.base`。

## High-Level Map

- Survey / review 主线：MER 数据集、预处理、特征抽取、fusion、benchmark、应用挑战。
- Foundation-model 主线：LLM/MLLM、prompt engineering、pretrained encoders、AffectGPT / EmoVerse 等情绪理解框架。
- Fusion 主线：early/late/hybrid fusion、attention fusion、cross-modal transformer、dynamic/expert-guided gating。
- Signal 主线：text、speech/audio、face/video、physiological signals，以及 conversation / multi-party context。

## Imported Papers

| Note | Year | Type | Venue | Citations | DOI | Title |
| --- | --- | --- | --- | ---: | --- | --- |
{chr(10).join(table_rows)}

## Next Actions

- 对需要正式写入 related work 的核心论文，优先补 PDF、抽取全文，再把对应 note 升级为 `pdf_backed: true`。
- 优先深读 survey 类和 MLLM 类条目：它们最可能帮助搭建多模态情绪识别基础模型的章节结构。
"""


def update_concept(links: list[str]) -> None:
    text = CONCEPT_PATH.read_text(encoding="utf-8")
    marker = "## Open Questions"
    heading = "## 2026-06-11 MER Related Work Cluster"
    section = f"""## 2026-06-11 MER Related Work Cluster

Consensus related-work CSV 导入了 {len(links)} 篇多模态情绪识别 / affective computing 候选文献，集中覆盖 survey、fusion、pretrained encoder、LLM/MLLM、conversation context 与 physiological signals。完整入口见 {SOURCE_NOTE_WIKILINK}；这些条目暂为 `pdf_backed: false`，正式写作引用前需要回到原文或 PDF。

### Candidate Papers

{chr(10).join(f"- {link}" for link in links)}

"""
    if heading not in text:
        text = text.replace(marker, section + marker)
        text = re.sub(
            r"paper_count: \d+",
            lambda m: f"paper_count: {int(m.group(0).split(': ')[1]) + len(links)}",
            text,
            count=1,
        )
    CONCEPT_PATH.write_text(text, encoding="utf-8")


def write_base() -> None:
    (BASES_DIR / "Multimodal Emotion Recognition Related Work.base").write_text(
        textwrap.dedent(
            f"""\
            filters:
              and:
                - type == "paper"
                - related_work_collection == "{COLLECTION}"
            views:
              - type: table
                name: MER Related Work
                order:
                  - file.name
                  - title
                  - authors
                  - published
                  - study_type
                  - citations
                  - venue
                  - doi
                  - concepts
                  - topics
                  - method_tags
                  - reading_evidence
                sort:
                  - property: published
                    direction: DESC
                  - property: citations
                    direction: DESC
            """
        ),
        encoding="utf-8",
    )


def main() -> None:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    links: list[str] = []
    for row in rows:
        path, content, link = paper_note(row)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and "pdf_backed: true" in path.read_text(encoding="utf-8"):
            links.append(link)
            continue
        path.write_text(content, encoding="utf-8")
        links.append(link)
    RESEARCH_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    (RESEARCH_NOTES_DIR / f"{SOURCE_NOTE_NAME}.md").write_text(source_note(rows, links), encoding="utf-8")
    write_base()
    update_concept(links)
    print(f"Imported {len(rows)} MER related-work rows.")
    print(f"Wrote {len(links)} paper notes, one source note, one base, and updated multimodal learning concept.")


if __name__ == "__main__":
    main()
