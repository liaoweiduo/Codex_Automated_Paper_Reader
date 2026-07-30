# Conference Paper Ingest Design

## Goal

Add a manually invoked conference-paper ingestion workflow that can retrieve a
complete released conference collection, reuse the existing research profile,
and write one grouped Obsidian knowledge note without changing the daily paper
schedule or its output files.

## Scope

- The first supported source is OpenReview, because ICML 2026 exposes a public
  OpenReview venue.
- The command accepts a conference name, year, and optional invitation override.
- It fetches the conference collection without the daily date-window filter.
- It reuses the existing paper schema, normalization, deduplication, and profile
  scoring logic.
- It writes isolated JSON/log/report output under a conference-specific directory.
- It writes one Markdown synthesis document under the configured Obsidian
  `Research Notes` directory. The document groups papers by configurable
  direction keywords and includes metadata, abstract, links, and retrieval
  evidence for every paper.
- It is not scheduled and does not modify the daily automation configuration.

## Non-goals

- No automatic LLM summarization is added to Python. Codex can analyze the
  generated candidate JSON and enrich the Markdown note after retrieval.
- No per-paper Obsidian note is created by default.
- No change to `daily_papers.py`, its CLI semantics, daily paths, or schedule.

## Architecture

`conference_papers.py` is a separate CLI and orchestration layer. It calls a
new OpenReview venue-fetch helper that shares the existing normalization helper
but does not share the daily date filtering. The orchestration layer scores and
groups normalized papers, writes a JSON snapshot and a Markdown report, and
uses an explicit Obsidian path so local vault layout is not hard-coded into the
daily pipeline.

The configuration is layered: `--config config.yaml` remains the source of the
research profile and OpenReview connection settings; conference-specific
options can be passed by CLI or an optional standalone conference config. The
default output remains inside `paper-daily/data/conferences/` and
`paper-daily/reports/conferences/`, leaving daily `data/`, `reports/`, and
`logs/` untouched.

## Data flow

1. Parse conference/year/venue/invitation/output arguments.
2. Load the existing config and research profile.
3. Resolve likely OpenReview invitations, preferring the explicit override.
4. Retrieve all available notes with pagination and normalize them.
5. Deduplicate by source ID and normalized title.
6. Apply the existing coarse profile score and assign direction labels from
   configured positive keywords and paper categories.
7. Write a JSON snapshot containing source counts, warnings, and papers.
8. Write a Markdown conference note with a generated table of contents,
   direction sections, and full paper metadata.

## Error handling

- A failed invitation is tried against the next compatible invitation.
- Pagination stops on an empty page, repeated IDs, or the configured maximum.
- If every invitation fails, the command exits non-zero and does not write an
  empty success artifact.
- Existing files are preserved unless `--force` is supplied.
- A partial page is reported in the JSON and Markdown warnings rather than
  being silently presented as a complete conference collection.

## Testing and verification

- Unit tests cover invitation resolution, pagination normalization, direction
  grouping, Markdown escaping, and output isolation.
- A mocked end-to-end command verifies that the conference output is created
  while the daily output directory is unchanged.
- A live ICML 2026 run is attempted after implementation; if OpenReview blocks
  the environment, the command's error and the local mocked verification are
  reported separately.
