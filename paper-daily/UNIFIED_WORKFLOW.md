# Unified Daily Reader — Codex 执行协议

工作目录固定为本文件所在 paper-daily。每次都重读 interests.json，不沿用旧 CS/PSY 提示词；不替用户改关注方向。使用 .venv/bin/python。Python 收集与下载，Codex 负责真实阅读、语义判断和中文写作；不调用额外模型 API。

## 1. 发现与覆盖状态

每次任务先执行 `.venv/bin/python scripts/unified_reader.py pending-downloads`，检查用户是否补交了等待中的 PDF。该命令更新 vault/Research Notes/待下载论文.md，并列出未完成任务。status=ready_for_reading 的任务必须优先处理：打开其 pdf_target，核对论文标题/DOI 与队列身份，使用 Python 抽取文本，按本协议精读并导出两张原图，更新已有 note（不重复建档）。完成后执行 `.venv/bin/python scripts/unified_reader.py resolve-download --key KEY --note "Papers/YYYY/原笔记.md"`，结构、证据和原图核验通过后才会标为 completed。发现本地 PDF 不代表读完；身份不匹配时明确报告，不误解读。没有新候选时也必须处理待解读队列。

先同步 Gmail Scholar 提醒（sources.google_scholar.transport=gmail 时）：

1. 使用 Gmail 连接读取当前 profile，必须确认账号与 interests.json 的 sources.google_scholar.email 一致；否则报告账号不符，不读取其他账户邮件。
2. 执行 `.venv/bin/python scripts/import_scholar_gmail.py plan --date yesterday`，把输出 query 原样用于 Gmail 搜索，分页读取直到 next_page_token 为空。仅访问命中的 Scholar 提醒邮件，不读取其他邮件。
3. 用 Gmail 读取命中消息的 HTML 正文（支持 MIME 子 parts）。先把所有消息整理为临时 JSON：`{"messages":[{"id":"消息id","internal_date":"毫秒时间戳","payload":{"mime_type":"text/html","headers":[{"name":"From","value":"scholaralerts-noreply@google.com"},{"name":"Date","value":"邮件日期"}],"body":{"content":"邮件中的论文 HTML"}}}]}`。只传 From/Date、消息id、到达时间和论文部分 HTML；不保存邮件私有头、取消订阅链接或跟踪链接。HTML 中标题链接应先解析 scholar_url 的 url 参数为论文原链接，删除页脚、取消订阅和分享部分。
4. 保存到 data/scholar-gmail-export.tmp，执行 `.venv/bin/python scripts/import_scholar_gmail.py import --export data/scholar-gmail-export.tmp --date yesterday`，成功后删除临时导出。Python 仅持久化论文标题、原链接、摘要片段、邮件来源id和到达日期，正文不是完整论文摘要时保留 alert-snippet 证据标记。
5. 搜索确认零条时仍导入 `{"messages":[]}`，记录“已同步、无新邮件”；连接失败、分页未完成或正文拿不到时，不得写空成功状态；删除本次日期已有的 data/scholar-inbox/_gmail_sync.json，避免复用过期的成功状态。记下覆盖缺口并继续其他来源。Gmail 当前读取成功不代表未来定时任务一定有连接权限，每次运行都要检查；缺工具/授权时明确报告，不能声称已自动同步。
6. 不标记已读、不移动、不删除或发送邮件。历史邮件只用于单独验证，不混入今天候选。

随后执行 `.venv/bin/python scripts/unified_reader.py fetch --date yesterday`。
OpenReview 的 auto_renew 已开启：fetch 内部读取项目外 ~/.config/capr/openreview.json，仅在凭证缺失、失效或剩余不足配置阈值时自动重新登录，申请最长 7 天的新凭证；以服务端实际 exp 为准。不要用文件读取工具查看、复制或打印密码配置，不把它写入 run.json 或报告。采集成功时复用现有凭证。重登单次请求限时 30 秒且每次任务只尝试一次；密码错误或需要站点/MFA 验证时，记录独立状态并继续其他来源，不要在后台打开输入密码窗口或循环重试。需要手动核验自动重登时使用 `.venv/bin/python scripts/openreview_auth.py renew --force`；正常运行不要强制重登。

以 Asia/Shanghai 的昨天为报告日期，三天回溯捕捉延迟发布；Scholar 用邮件送达日期，不伪造发表日期。
读取 `data/unified/YYYY-MM-DD/run.json` 和 `candidates.json`。本次运行后续使用 run.json 中 config_snapshot，若 interests.json 中途改变则停止重新 fetch，避免旧判断套新规则。
各来源独立失败；若部分失败，处理可用候选并在日报开头列覆盖缺口、HTTP 状态、需要的用户操作；全部失败时明确报告失败，绝不生成“今日无新论文”。
RSS 是最近窗口，API/类别列表有上限，不能声称穷尽全部论文。Source cap、缺摘要、缺日期、未配置 Scholar 都要注明。

## 2. 每条具体兴趣的语义判断

遍历所有 candidates（可分批读，不可只取前 100 篇）。结合 title、abstract、venue；缺摘要而疑似命中 level0/1 的，先访问论文页补证据再判断。queries 仅是检索提示，不是匹配规则；只有中文 label 也必须语义判断。泛词重合不算命中：SAE 只指 sparse autoencoder；THINGS 只指对应数据集及衍生数据，不能把普通 things 一词当证据。

输出 `data/unified/YYYY-MM-DD/decisions.json`，顶层数组，包含每篇候选一次（拒绝时 matches=[]）：

```json
[{"id":"原候选id", "matches":[{"topic":"interests 中 id；字符串条目则用原字符串", "confidence":0.92, "reason":"具体研究对象、方法与兴趣条目的关系；引用候选或正文的证据"}]}]
```

confidence 是语义判断强度，不是统计校准概率。阈值取 interests.json；level0 默认 >=0.7，level1 >=0.8，level2 >=0.6。多个条目同时命中，最高优先级控制动作，保留全部匹配理由。按相关性、研究问题的重要性、方法贡献、证据质量和与用户研究的可迁移价值综合排序，选最多 10 篇。候选不足可少于 10 篇，不为凑数降低标准；明确区分综述、预印本、应用论文和原创方法。按排序前 5 篇精读入库；因此 level2 若排入前 5 也作为用户新要求的例外精读入库。若某篇全文/图片暂不可得，保留其排名并如实标记缺口，不以占位图片冒充原图。

在候选全部语义判断后写 selection.json：`{"top10_ids":["按重要性排序的候选id"],"top5_ids":["top10排序前五篇的候选id"]}`。level0 命中但不在 Top 5 的论文仍触发关注提醒，不自动建档。

## 3. Python 下载与精读

**浙江大学机构访问**：对已选且需要全文的论文，Python 直接下载或公开作者稿无法取得时，优先尝试通过出版社官方机构登录入口使用浙江大学图书馆授权、本机 Chrome 的现有登录会话。若需要登录，可通过正常的浏览器密码管理器自动填充；不读取、输出、复制或另存密码、Cookie 或令牌。仅在浏览器和登录上下文实际可用时执行，不假设定时任务一定拥有桌面浏览器权限；如登录过期、需要用户交互或验证码、学校未订阅、浏览器不可用或网络异常，应分别记录并继续处理其他论文。确需用户操作时在日报和任务结果中报告，按既有规则保留待下载事项。取得 PDF 后核对标题或 DOI，再用于精读；不绕过访问控制或浏览器安全提示，不把机构授权视为所有出版社均有权限。

执行 `.venv/bin/python scripts/unified_reader.py prepare --date yesterday`。
读取 reading_queue.json；仅 selection.json 的排序前 5 篇独立精读建档；level2 在 Top 5 之外仅日报，不建长期笔记。
PDF/text/pages.json 存在 `data/unified/YYYY-MM-DD/papers/<reader_key>/`。失败时尝试公开作者版本、可信开放全文，严格核对标题/DOI；不绕过访问控制。用户提供本地 PDF 时放到队列给出的 papers/<reader_key>/paper.pdf，再重跑 prepare。

完整阅读全文的 introduction、method、experiments/results、limitations 与图注；读 pages.json 的页码与文字用于定位。下载成功不等于读完。不调用旧 process_conference_paper 的占位笔记生成流程。

先读 vault 的 Knowledge Protocol.md 和 Templates/Paper Note.md。按 DOI、arXiv id、标题查找 Papers/ 已有笔记，包括老 CS/PSY 笔记；优先更新现有文档，不因来源不同重复建档。新文档文件名 `Papers/YYYY/YYYY-MM-DD-unified - short-title.md`。

必须有 YAML：沿用模板字段，另加 interest_level、matched_interests、match_reasons、reading_status: complete/incomplete、figure_sources。daily_report 指向 `[[Daily Papers/unified/YYYY-MM-DD-unified]]`。authors、doi、published 等不可推测；note 的 year 为论文发表年份，缺失用发现年份。保留既有人工内容，合并补充而非整篇覆盖。

正文使用以下标题，每节实质解释，不留占位符：
- 一句话总结：解决什么、怎么做、主要发现和适用边界。
- 核心问题：已有方法的问题及本文研究假设。
- 核心方法：输入→模块/目标→训练/推断→输出；必要公式解释变量与直觉；指出相对近邻工作的实际变化。
- 核心内容配图：原论文最能说明核心贡献的框架/机制/任务设计图。说明图号、原页码、出处链接、各部分与方法步骤如何对应。
- 主实验配图：原论文支撑主 claim 的关键结果图；不是装饰图。解释坐标、图例、基线、数据集/样本、数值趋势及能/不能证明什么；结果主要在表格时截主结果表并标注。
- 实验设置与关键结果：任务/数据、样本量、比较方法、指标、主结果数值及出处页/表/图；必要消融、统计不确定性及代码/数据可用性。
- Claim 与证据：逐条判断直接支持/部分支持/不支持；AI 与人类行为表现相似不能等同认知机制相同。
- 局限：证据边界、失败条件、复现成本。
- 与关注方向的关系：命中哪条、为什么、可迁移的具体步骤。
- Links：论文页面、PDF、每日报告、已有 canonical Concepts/Ideas（只在有实质内容时更新，不制造同义词页面）。

## 4. 两张原图的导出与人工视觉核对

先用 figure 命令渲染候选页面查看，再依据实际页面选择裁剪框。页码从 1 开始，crop 为 PDF 点单位、左上角原点 x0 y0 x1 y1：

```
.venv/bin/python scripts/unified_reader.py figure --pdf PATH/paper.pdf --page 3 --output VAULT/Attachments/Paper\ Figures/KEY/core.png --crop 40 80 560 360
```

需要时先省略 crop 导出整页，读取图像后再裁剪；两张最终图片使用不同文件。正文嵌入 vault 相对路径 `![[Attachments/Paper Figures/KEY/core.png]]` 和 `![[Attachments/Paper Figures/KEY/main-results.png]]`。使用 view_image 实际查看导出图片，确认图号、内容、图例清楚且与本文一致，不截断轴标题。figure_sources 记录每张的论文 URL/DOI、图号/表号、页码、裁剪范围和角色。不得生成替代“原论文图”。

用户明确要求 Python 下载论文并在私有笔记保存关键原图：仅在合法可获得的材料与许可/授权范围内使用，标明来源，不公开再分发受限全文。无法合法获得原图时保留论文链接与文字证据，reading_status: incomplete，说明缺项；不能伪称满足精读完成度。

## 5. 日报、核验与提醒

写 vault/Daily Papers/unified/YYYY-MM-DD-unified.md，使用中文。包含覆盖状态、按重要性排序的 Top 10、Top 5 精读笔记链接、level0 关注清单、需要用户下载全文的清单。每篇 Top 10 都须高度概括具体问题、核心方法、关键证据、局限及相关性，并展示一张真正来自该论文的核心图（有清晰图号、页码和出处）；无法取得或不允许使用原图时明确标记缺图及原因，不以替代图或占位图冒充。Top 5 的每篇独立笔记须有论文核心图及主实验结果表或图，并按精读协议完整分析。已存在的论文可链接、补充，勿当全新发现反复推荐。

Top 5 全文不可得也建独立轻量记录，reading_status: incomplete、pdf_backed: false、reading_evidence: abstract-only/paper-page，写清缺全文/缺图，不编造方法实验。完整精读才标 durable/complete。

完成所有写入后保存 completion.json：
```json
[{"id":"原候选id","note":"Papers/2026/文件名.md"}]
```
其中只包含 Top 5。遇到全文不可得时，要先通过出版社页面核实访问状态；不能把超时、一般 HTTP 403、链接失效或缺少 PDF URL 当作付费墙。已核实的记录扩展为：

```json
[{"id":"原候选id","note":"Papers/2026/文件名.md","fulltext_status":"paywalled","access_evidence_url":"实际核实的出版社论文页","access_evidence":"页面明确显示订阅要求；已查找公开作者稿但未获得可用全文"}]
```

fulltext_status 只在明确付费时填 paywalled；需要机构认证时填 institutional_access_required。普通网络问题填 network_error，不能因此触发付费下载提醒。保存访问证据时引用实际页面，不编造付费状态。还应检查公开作者稿或合法开放版本，拿到可用全文时直接精读。

level0 命中且等待全文时发下载提醒；level1 除正常匹配阈值外，最高匹配 confidence >= interests.json/access_reminders/level1_min_confidence（默认 0.9）时，作为人工操作例外发下载提醒。level2 在 Top 5 之外仅日报；进入 Top 5 时按精读与用户补交全文规则处理。0.9 是语义判断阈值，不是统计概率。

执行：
`.venv/bin/python scripts/unified_reader.py finalize --date yesterday --notify`

finalize 核对每篇必需章节、完整证据、两张本地原图与图片文件存在性，输出 validation.json 和 alerts.json。已核实的付费全文缺口进入 data/unified/pending_downloads.json，并更新 vault/Research Notes/待下载论文.md；正文继续标 incomplete，不当作精读完成。此类明确等待用户下载且日报已存在的情况允许任务正常结束，结果明确列 awaiting_user_download。其他缺项返回非零，必须尽力修复。校验只证明结构，通过后仍必须核对文字与原图的科学内容。

日报必须有“需要你下载全文”小节：列论文标题、发表源、具体命中条目、契合原因、论文/机构访问链接、待办和笔记链接，给出清单中的 PDF 保存位置。下载提醒只在首次发生时发送，不每天重复；待办一直保留。用户可把 PDF 保存到清单的 pdf_target，或在聊天中附上 PDF 后由 Codex 放到对应位置。后续任务从 pending-downloads 继续处理，不能因发现日期已过去而遗漏。

提醒执行器使用本机 macOS 系统通知，标题“文献阅读提醒”，下载事项明确写“请下载全文”。level0 常规关注提醒和高匹配付费下载提醒分别去重，状态存 data/unified/state.json；level1 普通入库仍静默。仅有 level2 命中时不发送 level0 提醒；若 Top 5 中的 level2 论文高度匹配且全文付费，需要人工下载时可发送下载提醒。alerts.json 保留提醒内容；Obsidian 待办和日报提供持久记录。系统通知能否显示取决于通知权限/勿扰模式，脚本返回成功不保证横幅可见；没有邮件或手机推送渠道。保留自动化本身的既有通知策略，通知设置不写进自动化 prompt。


## OneDrive 运行存储（2026-11-24）

工作数据和临时文件的真实根目录为 `/Users/liaoweiduo/Library/CloudStorage/OneDrive-Personal/Researchs/obsidian sync/knowledge/Attachments/Paper Reader Workspace`，分别保存到 `data/` 与 `tmp/`。项目内的 `data`、`tmp` 仅为指向这些目录的兼容软链接，不得替换为本地真实目录。运行前核验两链接目标存在且可写；若 OneDrive 不可用，明确报告并停止依赖该存储的写入，不回退到仓库或系统临时目录。每日 fetch、prepare、figure、finalize 和辅助下载/导图均使用此存储；最终笔记、日报、PDF、图片继续保存到本 vault 原有对应目录。代码及 Python 环境保留在项目中。OneDrive 同步文件可能仍有本机缓存，云端同步完成与释放本机空间需由 OneDrive 状态确认。
