# Conference Paper Ingest Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manually invoked conference-paper fetcher that reuses the daily research profile and writes an Obsidian Research Notes knowledge document without changing daily behavior.

**Architecture:** Keep `daily_papers.py` unchanged. Add a separate `conference_papers.py` orchestration CLI and an OpenReview venue collection helper that uses the existing normalization and schema utilities but bypasses daily date filtering. Store conference artifacts in isolated directories and render one grouped Markdown note for Obsidian.

**Tech Stack:** Python 3, PyYAML, existing OpenReview/HTTP utilities, pytest, Markdown.

---

## Chunk 1: Collection and grouping core

### Task 1: Add failing tests for conference invitation and grouping behavior

**Files:**
- Create: `paper-daily/tests/test_conference_papers.py`
- Test: `paper-daily/scripts/conference_papers.py`

- [ ] Test explicit invitation precedence and ICML year invitation fallback.
- [ ] Test direction assignment from matched profile keywords and categories.
- [ ] Test Markdown output includes conference metadata, grouped sections, and paper links.
- [ ] Run `pytest tests/test_conference_papers.py -q` and confirm it fails because the new module is absent.

### Task 2: Implement the minimal conference orchestration module

**Files:**
- Create: `paper-daily/scripts/conference_papers.py`

- [ ] Add CLI arguments for config, conference, year, invitation, output directory, Obsidian root, max results, and force.
- [ ] Load the existing config and resolve conference-specific isolated paths.
- [ ] Call the venue collection helper, deduplicate, score, assign directions, and build a serializable payload.
- [ ] Render the one-file Markdown conference note.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Add the OpenReview complete-venue helper

**Files:**
- Modify: `paper-daily/scripts/fetch_openreview.py`
- Modify: `paper-daily/tests/test_conference_papers.py`

- [ ] Add a helper that tries explicit and generated invitations without applying the daily date window.
- [ ] Add bounded pagination for HTTP and client paths, stopping on empty or repeated pages.
- [ ] Preserve the daily `fetch_openreview` function and its date filtering unchanged.
- [ ] Add a mocked pagination test and run the focused test file.

## Chunk 2: Configuration, documentation, and verification

### Task 4: Add a reusable conference config example and usage docs

**Files:**
- Create: `paper-daily/config.conference.example.yaml`
- Modify: `paper-daily/README.md`
- Modify: `README.md`

- [ ] Document the manual ICML command and how to override the invitation after release.
- [ ] Document the default `Research Notes` path and the optional `--obsidian-root` override.
- [ ] State explicitly that no schedule is created and daily outputs are separate.
- [ ] Keep the example config profile-based and free of secrets.

### Task 5: Run full verification and inspect generated output

**Files:**
- No source changes expected.

- [ ] Run the full pytest suite from `paper-daily`.
- [ ] Run a mocked end-to-end conference command into a temporary output path.
- [ ] Attempt the live ICML 2026 command with a bounded result limit.
- [ ] Inspect JSON, Markdown, warning counts, and daily output paths.
- [ ] Run `git diff --check` and review `git status` to ensure unrelated user changes are preserved.
