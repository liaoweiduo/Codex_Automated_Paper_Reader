# Unified reader implementation plan

Goal: One existing daily automation; editable tiered topics; Python discovery/download; Codex semantic reading and illustrated Obsidian notes.

Architecture: Add an isolated unified command without changing old profiles or overwriting historical outputs. JSON controls topics and sources. Fetch records source health independently, preserves the whole retrieved pool, then accepts explicit Codex topic decisions. Prepare downloads PDFs and text; export selected original figure regions; finalize validates artifacts and emits only new level0 local alerts. Credentials stay outside Git.

- [x] Add JSON validation and deterministic routing tests, run red then green.
- [x] Add Nature RSS and Scholar alert-mail adapters with recorded coverage failures.
- [x] Add unified fetch, prepare, figure export and completion validation; no generated filler notes.
- [x] Document matching, copyright/access limits, source setup and exact Codex workflow.
- [x] Run tests, live source probes and a real PDF/figure smoke test.
- [x] Update existing CS automation and pause PSY, preserving schedule/model. Re-read saved state.

Decisions: Match natural-language topics semantically; English queries are optional recall aids. No fixed top-N archive quota. Highest matched tier wins. Abstract-only records remain explicitly incomplete until figures and full reading exist. Keep level1/2 silent via existing failed-runs-only policy, use local level0 notifications separately. Scholar email transport needs user setup; never claim it is already connected.

Verification (2026-10-29): 65 tests pass. Live Nature Human Behaviour RSS yielded 6 records for the selected 3-day window. Public SAE PDF download, text/page extraction and PNG rendering succeeded after one transient timeout; rendered title visually verified. Source probes: arXiv API/recent, OpenAlex, Nature/NHB/NMI/Nature Communications returned 200; Nature Neuroscience had a connection failure. OpenReview anonymous=403, stored token=401. Scholar mailbox delivery is intentionally user setup, not claimed connected. No fake paper note or synthetic daily report was written to the vault during smoke tests. Native notification invocation is unit-tested with a stub, not claimed delivered on this machine.

Automation readback: daily-reader renamed Daily Reader Unified ACTIVE, daily 01:00 schedule and existing model/effort preserved; daily-reader-psy PAUSED; monthly maintenance ACTIVE unchanged. Prior definitions backed up locally under paper-daily/.automation/backups (ignored by Git).

User setup remains: create Scholar email alerts with supplied keyword examples, then export selected alert messages to local inbox; renew/verify OpenReview access if needed; institutional login/download for restricted publisher full text. These setup limits are documented in SOURCE_SETUP.md.

Additional verification: selected-page crop export with top-left PDF-point coordinates succeeded; output visually checked against Figure 2 on paper page 3.

## Follow-up: Gmail connection (2026-10-29)

User connected Gmail. Profile confirmed liaoweiduo@gmail.com. Read-only Scholar sender searches and one historic thread validated. No Scholar alerts found in last 30 days or the exact current seven-day report window. Added Gmail connector -> sanitized metadata importer, MIME/base64 handling, snippet and PDF URL extraction, Shanghai date normalization, and per-date successful empty-sync state. Source config and automation-referenced workflow now use Gmail; .eml fallback remains. Historical sample imported with 2024 arrival date, verified excluded from current window. No mailbox mutations or new subscriptions performed. 67 tests pass. Next scheduled run must verify Gmail availability again; actual new-topic subscriptions still need user creation in Scholar.

## Source access audit follow-up (2026-10-29 15:33)

User reports Scholar subscriptions configured. Rechecked configured Nature/NHB/NMI/Neuroscience/Nature Communications feeds: all HTTP 200 with parseable entries. OpenAlex/PubMed/Europe PMC APIs HTTP 200 anonymously. OpenReview remains anonymous 403 and stored credential 401. Updated SOURCE_SETUP.md to replace obsolete Neuroscience outage status. Health evidence saved under ignored data/source-health/. No account settings or secrets changed.

## OpenReview script authentication handoff (2026-10-29)

User confirmed website login. Root cause: daily metadata SDK/HTTP paths ignored the credential used by PDF downloads. Added shared openreview_auth loader, wired SDK + HTTP fallback, retained shared PDF credential access. Added local interactive login .command using the official installed client with getpass and official MFA prompt. Password is not persisted; credential replacement is atomic, mode 0600, and conditional on a successful authenticated notes query. Runtime status exposes success/failure only. 70 tests pass (including previously failing auth propagation and safe replacement tests). Local login window opened for user input; actual login remains pending until metadata access succeeds. No success claim before live verification.

## Authentication failure root cause (2026-10-29)

User confirms correct password and MFA disabled. Traced generic RuntimeError to our post-login metadata gate; it conflated successful credential login with blocked paper endpoint and discarded the new token. Direct bounded probes returned ChallengeRequiredError for unfiltered/TMLR/ICLR queries; official SDK UA and proxy toggles had the same response. Added regression tests preserving official authenticated login session under metadata challenge; malformed login response cannot overwrite credentials. Separated metadata status from authentication; official returned challenge URL is opened only in user's browser, never solved or bypassed. 73 tests pass. Updated local login window opened once to acquire the session that the old gate discarded. Actual authenticated metadata recovery remains unverified pending user input and manual site verification.

Live follow-through: user's corrected helper login succeeded at 15:54:49; actual TMLR metadata request returned one paper and corresponding PDF returned 200 with valid signature. 73 tests pass after changes. Credential expiry is 2026-10-30 15:54:47 Asia/Shanghai. Official refreshToken endpoint probes returned MissingTokenError using header or cookie auth despite documented cookieAuth; inspecting the actual error before attempting changes. Long-term renewal is not yet claimed working.

Renewal investigation limitation: refreshToken returned 400 MissingTokenError / "No refresh token found" for both Authorization and access-token Cookie requests. This shows access credentials alone do not satisfy renewal; no unsupported refresh integration was added and no password was stored. Current access and PDF retrieval are confirmed restored. Credential renewal remains separate unfinished work; disclose the actual access expiry instead of promising permanent unattended authentication.

## File-backed automatic re-login (2026-10-29 16:20)

User filled the private project-external credential file and authorized integration. Added restricted config loading (owner-only mode, parameter bounds), actual token-expiry scheduling with independent API check, bounded one-attempt official /login request, 7-day lifetime request, safe error classification, private atomic credential replacement and retention on login failure. Unified OpenReview fetch now invokes this when auto_renew=true and degrades only that source on missing/unusable credentials. Password is never returned, logged or placed in config_snapshot.

Live `renew --force` succeeded using local credentials; server exp=2026-11-05T16:20:38+08:00, metadata HTTP 200. A subsequent normal `renew` returned reused, proving no repeated login while healthy. 80 tests pass including near-expiry renewal, forced login, credential leakage regression, file permission checks, challenge handling and other-source continuity. Existing Daily Reader Unified remains ACTIVE at daily 01:00 and reads the updated workflow; no extra automation created. Gmail profile confirmed; recent Scholar sender search still empty.

## Paid-paper download reminders (2026-10-29)

User requested reminders to obtain highly relevant paid full text and asked about delivery. Added publisher-evidence-gated paywall/institutional-access tasks, persistent deduplicated JSON + Obsidian Research Notes/待下载论文.md (preserves manual text around managed block), native Mac action notifications, daily report instructions, pending PDF detection and a validated resolution command. Level0 remains urgent; level1 paid/fulltext exceptions require confidence >=0.9 by default; level2 remains daily-only. Network/HTTP failures alone are not paywall evidence. Already-sent normal level0 alerts do not suppress a newly discovered download action; download notifications use a separate dedupe key. Missing full text stays incomplete; legitimate waiting-for-user tasks are reported separately from unexpected incomplete artifacts.

Each daily workflow checks pending PDFs before new discovery, verifies identity and reads figures before resolving. Current pending list initialized empty; no fake paid article or fake archived paper created. Updated interests preserve user edits to all topic levels; restored previously authorized Gmail transport/email fields that were missing after their edit, preventing an accidental return to EML-only discovery. Native notifications are local Mac only; no mail or phone push configured.
