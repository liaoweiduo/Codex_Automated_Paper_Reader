# paper-daily

`paper-daily` is the candidate-retrieval component of CAPR.

It fetches recent papers, normalizes metadata, deduplicates records, and writes a candidate JSON file for Codex to read. It intentionally does not write the final literature review.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell example:

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
```

## Fetch Candidates

```bash
python scripts/daily_papers.py --config config.yaml --date yesterday --stage fetch --force
```

Common options:

```bash
python scripts/daily_papers.py --config config.yaml --date 2026-05-15 --stage fetch --force
python scripts/daily_papers.py --config config.yaml --date yesterday --stage fetch --lookback-days 3
python scripts/daily_papers.py --config config.yaml --date yesterday --stage fetch --sources arxiv,openreview
python scripts/daily_papers.py --config config.yaml --date yesterday --stage fetch --sources openalex
python scripts/daily_papers.py --config config.behavior.yaml --date yesterday --stage fetch --force
```

`--date` accepts `today`, `yesterday`, or `YYYY-MM-DD`, and defaults to
`yesterday`. Daily automations should usually fetch `yesterday` so paper-source
batches have time to settle before Codex reads them.

## Manual conference collections

For a released conference collection, use the separate one-shot command. It
reuses `research_profile` and the OpenReview source settings from the selected
config, but does not use the daily date window and does not create a schedule:

```bash
python scripts/conference_papers.py \
  --config config.yaml \
  --conference ICML \
  --year 2026 \
  --candidate-limit 500 \
  --force \
  --obsidian-root "/Users/liaoweiduo/Library/CloudStorage/OneDrive-Personal/Researchs/obsidian sync/knowledge"
```

For ICML 2026 the command automatically uses the official virtual-site JSON
export, including its separate abstract export; this avoids the OpenReview API
challenge page while preserving OpenReview links in each paper record. For
other conferences, pass a matching official JSON export with `--source-url` and
`--abstracts-url`, or use the OpenReview invitation fallback with
`--invitation`. JSON and Markdown are isolated below
`data/conferences/icml-2026/`; the knowledge document is written to
`Research Notes/2026-icml-papers.md`.

会议流程会先按 `research_profile.positive_keywords` 过滤，再按 daily 的
`keyword_score` 和 `coarse_retrieval_score` 排序，默认只保留
500 条（可用
`--candidate-limit N`；`--max-results` 只控制源数据最多读取多少条。

生成 todo list 后，默认一次处理一篇并支持中断续跑：

```bash
python scripts/process_conference_paper.py \
  --queue data/conferences/icml-2026/papers.json \
  --obsidian-root "/Users/liaoweiduo/Library/CloudStorage/OneDrive-Personal/Researchs/obsidian sync/knowledge"
```

只有 PDF 下载、文本抽取、paper note 和已有 Concepts/Ideas 关联都成功后，队列标题才会从 `- [ ]` 变成 `- [x]`。
若 OpenReview PDF 返回 403，可在有权限时设置 `OPENREVIEW_ACCESS_TOKEN` 后重试；token 不写入配置文件。

OpenAlex is implemented as a first-class fetch source alongside arXiv and
OpenReview, but it is disabled by default in `config.yaml`. Enable it only when
you want OpenAlex works to enter the candidate pool directly; otherwise keep it
off and use arXiv/OpenReview as the daily primary sources. If you use an
OpenAlex API key, keep it outside Git and set it through the configured
`api_key_env` environment variable.

## Behavioral Psychology Pipeline

`config.behavior.yaml` is a deterministic daily retrieval profile for
behavioral psychology and adjacent fields. It does not ask Codex or any LLM to
search the web. Python source adapters fetch records from subscription/API-like
endpoints, normalize them into the candidate schema, deduplicate them, and write
the candidate JSON that Codex can later analyze.

Default daily source allocation is capped at 100 discovery records:

```text
OpenAlex      30  broad scholarly index
PubMed        25  behavioral medicine, cognitive neuroscience, psychiatry
PsyArXiv      15  psychology preprints through OSF
Crossref      20  target journal / ISSN table-of-contents retrieval
Europe PMC    10  open biomedical and behavioral-health literature
```

Semantic Scholar is optional enrichment only. It annotates already-discovered
records with citation metadata and open-access PDF hints; it does not add new
papers to the daily candidate pool.

Run the behavior profile:

```bash
python scripts/daily_papers.py --config config.behavior.yaml --date yesterday --stage fetch --force
```

Smoke-test one source at a time:

```bash
python scripts/daily_papers.py --config config.behavior.yaml --date yesterday --stage fetch --force --sources pubmed
python scripts/daily_papers.py --config config.behavior.yaml --date yesterday --stage fetch --force --sources psyarxiv
python scripts/daily_papers.py --config config.behavior.yaml --date yesterday --stage fetch --force --sources crossref
python scripts/daily_papers.py --config config.behavior.yaml --date yesterday --stage fetch --force --sources europepmc
python scripts/daily_papers.py --config config.behavior.yaml --date yesterday --stage fetch --force --sources openalex,pubmed,psyarxiv,crossref,europepmc
```

The source adapters are:

```text
scripts/fetch_pubmed.py
scripts/fetch_osf_psyarxiv.py
scripts/fetch_crossref.py
scripts/fetch_europepmc.py
scripts/enrich_semantic_scholar.py
```

## API Keys and Local Setup

Most sources work without private credentials. Keys improve quota or politeness,
and should be kept outside Git.

Set environment variables in your shell, launchd job, or automation runner:

```bash
export NCBI_EMAIL="you@example.com"
export NCBI_API_KEY="..."
export OPENALEX_API_KEY="..."
export SEMANTIC_SCHOLAR_API_KEY="..."
```

Then keep the config fields as env-name references:

```yaml
pubmed:
  email: ""
  api_key_env: NCBI_API_KEY
openalex:
  api_key_env: OPENALEX_API_KEY
semantic_scholar:
  api_key_env: SEMANTIC_SCHOLAR_API_KEY
```

User TODO list:

1. Add your real email to `NCBI_EMAIL`; NCBI recommends identifying API users.
2. Optional: request an NCBI API key from your NCBI account and set
   `NCBI_API_KEY` for higher E-utilities rate limits.
3. Optional: set `OPENALEX_API_KEY` if you have one; otherwise OpenAlex still
   works for normal daily use.
4. Optional: request a Semantic Scholar Graph API key and set
   `SEMANTIC_SCHOLAR_API_KEY` if enrichment becomes rate-limited.
5. Add or adjust Crossref ISSNs in `config.behavior.yaml` for the journals you
   actually want to follow.
6. If you have institutional access to PsycINFO/EBSCO, add that as a separate
   future source instead of routing it through LLM web search.

Outputs:

```text
data/raw/YYYY-MM-DD.json
data/processed/YYYY-MM-DD_candidates.json
logs/YYYY-MM-DD.log
```

Runtime outputs are ignored by Git.

The raw JSON includes a `duplicate_check` block. If `status` is
`duplicate_of_previous`, or either the top-level or `duplicate_check`
`recommended_action` is `write_no_new_batch_note`, the target-date final
candidate pool is empty or has the same paper IDs as the most recent previous
candidate file. Codex should write a short "no new candidate batch" note instead
of repeating the prior Top 10.

For arXiv, CAPR treats the HTML recent-list heading date as the authoritative
daily announcement date. If no papers are listed for the target date, it does
not reuse the latest older batch; the raw JSON will recommend the same short
no-new-batch note.

## Network Preflight

Before fetching, the script checks core source URLs for enabled sources. If
these checks fail, the script exits before writing an empty candidate file.

CAPR ignores environment proxy variables by default for source requests, because some automation sandboxes expose broken local proxy settings. If you need to use your system proxy, set:

```bash
PAPER_DAILY_USE_ENV_PROXY=1
```

## Candidate Schema

Each candidate includes:

```json
{
  "id": "...",
  "source": "arxiv",
  "title": "...",
  "authors": ["..."],
  "abstract": "...",
  "url": "...",
  "pdf_url": "...",
  "published_at": "...",
  "updated_at": "...",
  "venue": "...",
  "categories": ["..."],
  "keyword_score": 0.0,
  "retrieval_reason": "why the retrieval script kept this candidate",
  "matched_keywords": [],
  "negative_matches": [],
  "coarse_retrieval_score": 0.0,
  "doi": "...",
  "citation_count": 0,
  "influential_citation_count": 0,
  "semantic_scholar_id": "...",
  "semantic_scholar_url": "..."
}
```

The retrieval scores and citation metadata are only hints. Codex should still
perform semantic reading and scoring before writing the final report.

## Tests

```bash
python -m pytest tests
```

## 统一分层阅读流程（2026-10-29）

现在日常任务使用 [interests.json](interests.json)：编辑 level0/level1/level2，移动条目即可改变提醒与入库策略。支持直接中文字符串，也支持 `{"id":"固定标识","label":"具体研究问题","queries":["英文检索短语"]}`。level0 为提醒+独立笔记，level1 为高匹配独立笔记，level2 仅日报。默认示例分别为 SAE 优化、THINGS、AI × 认知心理，可自由改动。

```bash
.venv/bin/python scripts/unified_reader.py check
.venv/bin/python scripts/unified_reader.py fetch --date yesterday
# Codex 语义判断并写 decisions.json 后：
.venv/bin/python scripts/unified_reader.py prepare --date yesterday
# Codex 完成含两张原图的笔记、日报及 completion.json 后：
.venv/bin/python scripts/unified_reader.py finalize --date yesterday --notify
```

执行协议：[UNIFIED_WORKFLOW.md](UNIFIED_WORKFLOW.md)。来源及逐步登录设置：[SOURCE_SETUP.md](SOURCE_SETUP.md)。输出：`data/unified/YYYY-MM-DD/`；日报：knowledge/Daily Papers/unified/。所有原历史 CS/PSY 输出保留；月度知识维护任务独立保留。此功能不调用模型 API，不需要新增 OpenAI key。

OpenReview 自动重登已启用：私密账号密码由用户保存在项目外 `~/.config/capr/openreview.json`（权限 600）；统一 fetch 自动检查并在剩余不足 24 小时时重新登录，申请 7 天凭证。不要将私密配置写入项目或日志。手动验证用 `.venv/bin/python scripts/openreview_auth.py renew`，强制验证用 `renew --force`。
