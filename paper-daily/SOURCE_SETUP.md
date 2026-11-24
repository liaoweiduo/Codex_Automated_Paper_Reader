# 来源与登录设置

2026-10-29：默认配置为 interests.json；从仓库根目录运行 `paper-daily/.venv/bin/python paper-daily/scripts/unified_reader.py check`。自动化从 paper-daily 目录执行。

## 1. Google Scholar：先设置提醒邮件

1. 打开 https://scholar.google.com/，建议先登录自己的 Google 账号，方便统一管理提醒。
2. 搜索具体检索词，在结果左栏点击信封 Create alert / 创建提醒。
3. Email 字段填接收邮箱，点击 Create alert；如收到验证邮件，按邮件完成确认。每组检索式建立一个提醒。
4. 在 Scholar 菜单 Alerts / 提醒管理现有订阅，误报多时细化词组，漏检时另建一个同义表达；不必把所有词堆进同一个查询。

建议先建立以下独立查询（双引号限定词组）：

| 对应方向 | 查询 |
|---|---|
| SAE 优化 | `"sparse autoencoder" optimization` |
| SAE 训练 | `"sparse autoencoder" training` |
| SAE 特征质量 | `"sparse autoencoder" "feature quality"` |
| THINGS | `"THINGS dataset"` |
| THINGS 衍生数据 | `"THINGS-EEG"`、`"THINGS-MEG"`、`"THINGS-fMRI"`，各一条 |
| 人类认知与模型 | `"language models" "human cognition"` |
| AI 与认知心理 | `"artificial intelligence" "cognitive psychology"` |

Scholar 搜索词负责邮件召回；JSON 中文 label 负责 Codex 语义筛选。引号过多会漏检，先用这些具体组合，再根据实际邮件调整。无须写 continual learning 等泛方向。

接入状态（2026-10-29）：Gmail 已连接并核对为 liaoweiduo@gmail.com。实测成功读取历史 Scholar 提醒，提取论文标题、论文链接与摘要片段。近 30 天未找到此发件人的提醒，不代表新关注主题已成功订阅；请在 Scholar 的 Alerts 页面检查新查询。

统一自动化现在会先通过 Gmail 连接检索近期 Scholar 提醒，再由 Python 导入论文元数据到 `data/scholar-inbox/gmail-*.json`；不需要手动导出 `.eml`。Gmail 搜索与读取由 Codex 的授权连接完成，Python 不存 Gmail 密码或 OAuth 令牌。每次任务检查当前账号与权限；连接不可用时如实报告来源缺口。

备用方式仍支持把单封 Scholar 提醒导出 `.eml` 到 `paper-daily/data/scholar-inbox/`。不导出整个私人邮箱。按 Asia/Shanghai 的邮件送达日期筛选，不把送达日当发表日。

官方帮助：https://scholar.google.com/intl/en/scholar/help.html 。官方要求自动程序遵守 robots.txt；本项目使用提醒邮件，不抓取 Scholar 搜索页面。

## 2. OpenReview：本地脚本认证已恢复

2026-10-29 15:55 认证恢复：官方账号登录成功，新凭证已保存。已通过真实 TMLR 元数据适配器读取一篇论文，并验证其 PDF 返回 200 且内容具有 PDF 文件签名。此前匿名 403 和旧凭证 401 为历史状态。

1. 在浏览器登录 https://openreview.net/，确认目标论文页面与 PDF 能打开。
2. 如果仍无法打开，先更换可访问网络或联系站点；不要不断重试或绕过验证码。
3. 项目 PDF 下载支持既有 `OPENREVIEW_ACCESS_TOKEN` 环境变量或本地 `.openreview_access_token` 文件；不要把令牌写进 interests.json、聊天或 Git。元数据采集、HTTP 回退和 PDF 下载现在共用本地认证凭证。浏览器登录不自动传给 Python。若认证仍失败，日报会标记覆盖缺口。
4. 需要立即精读时，可用浏览器正常下载有权限的 PDF，放入 reading_queue.json 对应的 `papers/<reader_key>/paper.pdf` 后重跑 prepare。

## 3. Nature 与子刊

RSS 元数据不需要账号。默认覆盖 Nature、Nature Human Behaviour、Nature Machine Intelligence、Nature Neuroscience、Nature Communications。

2026-10-29 15:33 复查：Nature、NHB、NMI、Nature Neuroscience、Nature Communications 五个 RSS 均返回 200 且解析成功。此前 Nature Neuroscience 的连接错误已恢复，无需修改订阅地址或登录。

全文与原图受访问权限影响。若遇付费墙：在浏览器打开论文 → 选择机构登录/Access through your institution → 按学校图书馆要求登录或使用校外访问 → 正常下载有权访问的 PDF → 放入对应本地待处理目录。不需要把学校密码交给脚本。没有访问权限时先找公开作者稿；仍不可得则建轻量待补全记录，不声称精读完成。

## 4. arXiv 与其他公开索引

- arXiv：无需登录；本次 API 与 cs.LG recent 页面返回 200。按类别抓取近期论文，包含列表数量上限，不能保证全量。
- OpenAlex：本次匿名 works 请求返回 200；需要更高配额时在官方账号申请 key，设置 `OPENALEX_API_KEY`。无需把 key 写入 JSON。
- PubMed / Europe PMC：默认匿名检索；NCBI key 可选，使用 `NCBI_API_KEY`。各查询分配独立召回预算，避免第一个方向占满全部名额。
- OpenReview 负责部分 AI 主流会议；OpenAlex 作为期刊/会议补充索引，不代表所有会议全文都可用。

## 5. Level0 本地提醒

自动化保持既有“仅失败通知”。level0 由独立本地 macOS 通知触发，level1 普通入库和 level2 不触发提醒；level1 高度匹配且核实全文付费时，作为需要人工操作的例外提醒。macOS 如拦截通知，在“系统设置 → 通知”允许实际发送程序的通知；脚本调用成功不保证系统横幅在勿扰模式下可见。当天 alerts.json 始终保留提醒清单，state.json 避免跨日重复。可先不加 `--notify` 检查提醒内容，确认后加上。

## 6. OpenReview 自动重登与本地配置

用户已配置 `~/.config/capr/openreview.json`，文件权限 0600，位于项目与同步盘之外。它包含用户自行填写的账号密码，以及 `token_expires_in_seconds`、`renew_before_expiry_hours`；不要在聊天、日志、日报或候选 JSON 中复制此文件内容。

`interests.json` 的 `sources.openreview.auto_renew: true` 已开启。每天统一采集进入 OpenReview 时自动检查已缓存凭证的实际到期时间和接口访问状态：

1. 凭证正常、剩余超过配置阈值时直接复用。
2. 凭证缺失、失效或剩余不足 24 小时时，通过官方 `/login` 重新登录，申请 604800 秒的凭证；采用服务器实际返回的 `exp`。
3. 新凭证以 0600 权限原子保存到 `.openreview_access_token`，元数据 SDK、HTTP 回退和 PDF 下载共用此文件。
4. 每个任务只尝试一次自动登录，请求限时 30 秒；失败不输出服务器原始报错，不覆盖旧凭证。旧凭证仍经验证可用时继续使用，否则记录 OpenReview 缺口并继续其他来源。
5. 遇到站点验证或启用 MFA 等人工操作要求时，不在后台弹输入框或循环尝试。诊断状态位于 `data/openreview-auth/status.json`；用户自行修改密码后更新私密文件即可。

2026-10-29 16:20 已实测：读取用户填写的私密配置，自动重登成功，服务端实际签发 7 天凭证，有效至 **2026-11-05 16:20:38（Asia/Shanghai）**；论文接口 HTTP 200。随后再次运行正常检查返回 `reused`，没有重复登录。自动重登接在现有每日任务内，不需要另建自动化。

手动检查（从 paper-daily 目录运行）：

```bash
.venv/bin/python scripts/openreview_auth.py renew
.venv/bin/python scripts/openreview_auth.py check
```

仅需明确测试密码配置时使用 `renew --force`。不要配置一个长期静态 `OPENREVIEW_ACCESS_TOKEN` 环境变量，它会遮蔽更新后的缓存文件；当前环境不存在该冲突。

交互备用入口仍为 `OpenReview 登录.command`。此入口本身不保存你输入的密码，适用于手动恢复；自动登录使用的是你自行填写的项目外私密配置。密码保存在本机明文 JSON 是用户当前选择的方式，以后可以改用系统钥匙串。

官方客户端参数说明：https://openreview-py.readthedocs.io/en/latest/api.html 。这里使用自动重新登录签发新凭证，没有依赖先前未通过验证的 `/refreshToken` 路径。

## 7. 尚需注意的范围

- Scholar 新订阅不会自动改变 `interests.json` 的分级范围；当前关注条目与层级以 JSON 为准；新增 Scholar 订阅时仍需同步编辑 JSON。
- Gmail 连接仍正常；2026-10-29 再次搜索近七天 Scholar 提醒，结果为空。用户已确认订阅设置完成，等待首封新提醒到达，不能把历史测试邮件当今天的新论文。
- 本轮验证覆盖真实认证、元数据、PDF、图片导出及自动重登；完整的每日 Codex 精读、写库与通知链仍需在实际完整运行中验收。

## 8. 高匹配付费论文提醒

已加入下载待办：`Research Notes/待下载论文.md`。确认付费或需机构认证的论文会记录标题、匹配原因、访问页面、笔记和 PDF 保存位置；一般网络失败不冒充付费墙。Mac 系统通知会写“请下载全文”，当天日报也列人工操作清单。level0 正常提醒；level1 的付费例外阈值默认 0.9，可在 interests.json/access_reminders 中调整；level2 仍仅日报。重复运行不重复新增任务或重复发送同一下载提醒。

下载后把 PDF 放到清单指定位置，或在聊天里附上。每日任务先检查 pending-downloads，发现文件后继续精读、原图和笔记；核验通过才标完成。当前没有配置邮件或手机推送，Mac 横幅受系统通知权限/勿扰影响；待办与日报持久保存。


## OneDrive 运行存储（2026-11-24）

工作数据和临时文件的真实根目录为 `/Users/liaoweiduo/Library/CloudStorage/OneDrive-Personal/Researchs/obsidian sync/knowledge/Attachments/Paper Reader Workspace`，分别保存到 `data/` 与 `tmp/`。项目内的 `data`、`tmp` 仅为指向这些目录的兼容软链接，不得替换为本地真实目录。运行前核验两链接目标存在且可写；若 OneDrive 不可用，明确报告并停止依赖该存储的写入，不回退到仓库或系统临时目录。每日 fetch、prepare、figure、finalize 和辅助下载/导图均使用此存储；最终笔记、日报、PDF、图片继续保存到本 vault 原有对应目录。代码及 Python 环境保留在项目中。OneDrive 同步文件可能仍有本机缓存，云端同步完成与释放本机空间需由 OneDrive 状态确认。
