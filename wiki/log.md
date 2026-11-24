# Log

Chronological record of operations on this wiki. Append-only.

Each entry starts with `## [YYYY-MM-DD] action | title` so the log is greppable:

```bash
grep "^## \[" wiki/log.md | tail -20
```

Maintained by `scripts/append_log.py`.

---

## [2026-05-29] bootstrap | Wiki initialized
Topic: A research wiki for distilling daily AI and machine learning paper discovery into durable knowledge about methods, concepts, papers, findings, and open research questions.

## [2026-05-29] schema-evolve | Daily paper distillation rules
Documented the CAPR convention: after each paper-daily report, keep only durable papers and update sources, concepts, notes, index, log, and hot cache.

## [2026-05-29] lint | Health check
Wrote wiki/reports/lint-2026-05-29.md. 0 block, 0 quality, 0 suggestion.
