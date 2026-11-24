# CAPR Research Wiki

> A personal LLM-managed wiki using the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Maintained with the `llm-wiki-manager` skill.
> The LLM (Claude) owns all writing in `wiki/`. The user owns `raw/`. This file is the schema.

## Purpose

A research wiki for distilling daily AI and machine learning paper discovery into durable knowledge about methods, concepts, papers, findings, and open research questions.

This wiki belongs to the CAPR workflow: `paper-daily` retrieves and ranks daily
candidate papers, while this wiki preserves the smaller set of ideas that should
compound across days. Daily reports are ephemeral reading surfaces; the wiki is
the durable research memory.

## Layers

- `raw/` — immutable sources, user-curated. Read but never modify.
- `wiki/` — LLM-managed pages. Owned by Claude. The user reads, doesn't write.
- `CLAUDE.md` (this file) — schema. Co-evolved with the user as conventions emerge.

## Structural files

Always in `wiki/` root — maintained by the LLM, never by hand:

- `wiki/index.md` — content catalog by category; updated by `scripts/update_index.py` on every ingest.
- `wiki/log.md` — append-only operation log; updated by `scripts/append_log.py` on every ingest/query/lint.
- `wiki/hot.md` — ~500-word hot cache (vault state, latest ingests, open items, tag inventory); **rewritten entirely** after every ingest.

## Categories

Default layout, with CAPR-specific conventions.

- `wiki/sources/` — one summary page per ingested source.
- `wiki/entities/` — people, organizations, products, places.
- `wiki/concepts/` — ideas, theories, terms-of-art, frameworks.
- `wiki/notes/` — workflow notes, filed-back query answers, synthesis notes, and open research threads.
- `wiki/reports/` — auto-generated lint and audit reports, dated. The LLM does not author content here; scripts do.

When daily paper ingestion becomes dense enough to strain `wiki/sources/`,
introduce `wiki/papers/` and document that migration here before moving pages.

## Conventions

- **Slugs:** lowercase-with-hyphens. `michael-pollan.md`, not `Michael Pollan.md`.
- **Source filenames in `raw/`:** `YYYY-MM-author-short-title.ext` (recommended; not enforced).
- **Wiki links:** standard markdown, relative paths. `[Title](../entities/title.md)`.
- **Frontmatter:** optional. If used, keep keys consistent (`tags`, `updated`, `sources`).
- **Citation style:** in-line as `(see [Source Title](../sources/source-slug.md))`.

## External Wiki (optional)

<!-- Fill in if this project wiki connects to a long-lived global wiki (personal
     knowledge base, Obsidian vault, second brain). Required for any multi-wiki
     operation. The agent reads this section on session start and routes writes
     accordingly. See references/multi-wiki-routing.md for the four canonical
     scenarios (write-to-global, pull-from-global, promote, dual-lint).

Global knowledge base path: ~/Documents/obsidian/
(Change to your actual path, or delete this whole section if you only use one wiki.)

Routing rules:
- Project-specific code decisions, architecture, bugs, API contracts → this wiki
- General concepts, frameworks, patterns reusable across projects → global wiki
- Source summaries for internal/project docs → this wiki
- Source summaries for books, papers, general articles → global wiki
- When the user says "global wiki", "obsidian", "my notes" → use global path
- When routing is ambiguous → ask one clarifying question before writing
- Scripts always need `--path` pointing to the right wiki root

Cross-wiki link convention:
- Use absolute paths: ~/Documents/obsidian/wiki/concepts/foo.md
- Never use relative paths that cross wiki boundaries (they break under directory
  moves and git history rewrites)
-->


## Page structure

### Daily paper distillation (`wiki/notes/daily-paper-distillation-workflow.md`)

After each daily paper collection/report, Codex should decide which papers deserve
long-term memory. Do not ingest the whole report mechanically. Preserve papers
that meet at least one of these criteria:

1. Directly advances the user's research profile: sparse representation,
   compositionality, multimodal learning, continual learning, test-time
   adaptation, alignment, multi-objective optimization, or vision-language models.
2. Introduces a reusable method, dataset, benchmark, evaluation protocol, or
   theoretical framing likely to matter beyond one news cycle.
3. Connects to an existing wiki concept or creates a promising new concept page.
4. Raises an open question worth tracking across future papers.

For each kept paper, create or update a source summary and any relevant concept
pages. Record why the paper was kept and how it connects to prior wiki knowledge.
For papers that are interesting but not durable, leave them in the daily report
only.

### Source summary (`wiki/sources/<slug>.md`)

1. One-line summary at the top
2. Key claims (bullets, each with location citation — page, timestamp, paragraph)
3. Evidence quality / methodology
4. How it relates to existing wiki pages (explicit links)
5. Notable quotes (sparingly)
6. Open questions

### Entity (`wiki/entities/<slug>.md`)

1. One-line description
2. Background
3. Key positions / contributions / events (each with source citation)
4. Disputes (when sources disagree)
5. Sources (list of source-summary pages cited)

### Concept (`wiki/concepts/<slug>.md`)

1. Definition (one or two sentences)
2. Origin
3. Key claims
4. Disputes
5. Related concepts (links)
6. Sources

## Bookkeeping discipline

Apply on every operation:

1. **Log every operation.** Use `scripts/append_log.py`. Format: `## [YYYY-MM-DD] action | title`.
2. **Update the index** for every new or substantially-updated page. Use `scripts/update_index.py`.
3. **Rewrite `wiki/hot.md` after every ingest.** Do not append — rewrite entirely. Update vault state, active knowledge (latest ingest at top), open work items, tag inventory.
4. **Cross-reference aggressively.** When ingesting a source about an entity that already has a page, update that page in place. Don't leave the connection in the source summary alone.
5. **Cite back to sources.** Every claim should be traceable to a specific source.
6. **Flag contradictions.** When new sources disagree with existing claims, add both with citations and note the conflict. Never silently overwrite.

## Workflow notes

- Daily cadence: after `paper-daily` produces `paper-daily/reports/YYYY-MM-DD.md`,
  Codex should read that report and the matching candidate metadata when useful,
  select only durable papers, then write distilled knowledge into `wiki/`.
- Selection is conservative: prefer 1-5 durable papers over copying the whole
  daily Top 10. If no paper clears the bar, append a short log note instead of
  creating low-value pages.
- Each kept paper gets a source page with: one-line contribution, method or
  mechanism, why it matters to the user's research profile, links to related
  concepts, evidence limits, and follow-up questions.
- Concept pages should be updated whenever a paper strengthens, weakens, or
  complicates a tracked idea. Do not leave reusable insights trapped inside a
  source page.
- Use `wiki/notes/` for cross-paper synthesis, open research threads, and daily
  distillation decisions that are broader than one paper.
- Lint cadence: run `lint_wiki.py` after roughly every 10 ingests or after any
  larger restructuring.

## Tooling

- Scripts in `scripts/` (init_wiki, append_log, update_index, lint_wiki). Always prefer the scripts to hand-editing structural files.
- The wiki is a git repo; commit after substantive changes so rollback is easy.
