---
type: hot
domain: meta
created: 2026-05-29
updated: 2026-05-29
---

# Hot

Hot cache — a ~500-word summary of recent ingests and currently active context. In cross-project link scenarios, other projects read this file first. **Rewrite entirely after every ingest** — do not append. Older content is findable via the index and log.

## Vault state

- Structure: categorical `wiki/sources/`, `wiki/entities/`, `wiki/concepts/`, `wiki/notes/`, and script-generated `wiki/reports/`.
- Page count: **1 authored wiki note** + **0 raw sources**. No paper sources have been ingested yet.
- Main themes: daily AI/ML paper triage, durable research memory, sparse representation, compositionality, multimodal learning, continual learning, test-time adaptation, alignment, multi-objective optimization, and vision-language models.

## Active knowledge (most recently learned)

- [Daily Paper Distillation Workflow](notes/daily-paper-distillation-workflow.md) defines the CAPR convention: after each `paper-daily` report, keep only papers with long-term research value and write distilled knowledge into source, concept, and synthesis pages.

## Vault-specific decisions

- Wiki initialized 2026-05-29.
- Daily reports are not copied wholesale into the wiki. Codex should conservatively select durable papers, usually 1-5 per day.
- Reusable insights should be promoted from source summaries into concept pages during ingest.
- If no daily paper clears the durability bar, log the review without creating filler pages.

## Open work items

- After the next `paper-daily/reports/YYYY-MM-DD.md` is generated, run the daily distillation workflow.
- Decide later whether dense paper coverage warrants introducing `wiki/papers/` in addition to `wiki/sources/`.

## Tag inventory (current)

- `#workflow`
- `#paper-daily`
- `#research-memory`
