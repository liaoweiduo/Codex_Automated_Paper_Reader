# Daily Paper Distillation Workflow

This note defines how CAPR turns daily paper reports into durable wiki knowledge.
`paper-daily` collects and ranks candidates; this wiki keeps only the ideas that
should remain useful across weeks or months.

## Inputs

- Daily report: `paper-daily/reports/YYYY-MM-DD.md`
- Candidate metadata: `paper-daily/data/processed/YYYY-MM-DD_candidates.json`
- PDFs or extracted text under `paper-daily/tmp/` when deeper reading is needed
- Research profile in `paper-daily/config.yaml`

## Keep Criteria

Keep a paper when it satisfies at least one condition:

1. It directly matches the user's long-term interests: sparse representation,
   compositionality, multimodal learning, continual learning, test-time
   adaptation, alignment, multi-objective optimization, or vision-language models.
2. It introduces a reusable method, benchmark, dataset, evaluation protocol,
   failure mode, or theoretical framing.
3. It updates an existing wiki concept or deserves a new concept page.
4. It creates a concrete open research question worth revisiting.

Do not ingest papers solely because they ranked highly in the daily report.
Interesting but low-durability papers should remain in the report.

## Daily Procedure

1. Read the daily report and, if needed, the processed candidate JSON.
2. Select a small durable set, usually 1-5 papers.
3. For each kept paper, create or update a source page in `wiki/sources/`.
4. Update related concept pages immediately; do not leave reusable insights only
   in the source summary.
5. Add synthesis or open-question notes in `wiki/notes/` when multiple papers
   point at the same direction.
6. Update `wiki/index.md`, append `wiki/log.md`, and rewrite `wiki/hot.md`.

## Source Page Minimum

Each kept paper summary should include:

- One-line contribution
- Method or mechanism
- Why it matters to the research profile
- Relation to existing wiki pages
- Evidence limits or assumptions
- Follow-up questions

## No-Keep Days

If no paper clears the durability bar, do not create filler pages. Append a log
entry noting that the daily report was reviewed and no durable ingest was made.
