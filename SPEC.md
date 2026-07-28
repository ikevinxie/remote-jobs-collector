# 全球远程工作岗位每周收集 — 规格说明

> 状态:v1.0 已确认(2026-07-11)
> 协作规范:① 先 Spec 探讨再开发;② 所有产出必须积累测试用例。

## 1. 目标

每周自动从多个免费公开渠道采集全球远程工作岗位,统一数据模型、跨源去重后存入本地 SQLite 数据库,并生成一份中英双语 Markdown 周报。

## 2. 数据源(第一期,全部免费,无需付费 API)

| # | 渠道 | 接口 | 形式 |
|---|------|------|------|
| 1 | Remotive | `https://remotive.com/api/remote-jobs` | JSON API |
| 2 | We Work Remotely | `https://weworkremotely.com/remote-jobs.rss` | RSS |
| 3 | RemoteOK | `https://remoteok.com/api` | JSON API(使用时周报中注明出处链接) |
| 4 | Jobicy | `https://jobicy.com/api/v2/remote-jobs` | JSON API |
| 5 | Himalayas | `https://himalayas.app/jobs/api` | JSON API |
| 6 | Working Nomads | `https://www.workingnomads.com/api/exposed_jobs/` | JSON API |
| 7 | HN Who's Hiring | Algolia HN Search API(见 §15) | JSON API(月更帖,周采增量) |
| 8 | 电鸭社区 | `svc.eleduck.com/api/v1/posts?category=5`(见 §24) | JSON API(中文社区,只收企业直招+全职远程) |
| 9 | V2EX | `www.v2ex.com/api/topics/show.json?node_name=remote/jobs`(见 §25) | JSON API(中文社区,每节点最新 10 帖) |
| 10 | Indeed 邮件 | 用户 QQ 邮箱内 Indeed 职位提醒邮件,IMAP 拉取(见 §27) | 半自动(标准库 imaplib,读用户自己收到的邮件,不爬 Indeed) |
| 11 | 小红书 | 博主分享的远程岗位,用户截图 → 会话视觉提取(见 §28) | 半手动 ingest(小红书无公开 API 且风控强,不自动采集) |
| 12 | LinkedIn 邮件 | 用户 QQ 邮箱内 LinkedIn Job Alerts 邮件,IMAP 拉取(见 §29) | 半自动(同邮箱共用凭据,只留 Remote/Hybrid,不爬 LinkedIn) |

- 任一源失败不阻塞整体流程,周报中标注该源当周采集失败。
- 明确不做:**直接爬** LinkedIn/Indeed/小红书(违反 ToS 或需付费/需登录风控);ATS 定向抓取(留 M3 备选)。
  - Indeed / LinkedIn:官方免费求职 API 已停/受限,直接爬违反 ToS;改为**解析用户自己 QQ 邮箱里收到的求职提醒邮件**(Indeed §27、LinkedIn §29),合法且稳定。
  - 小红书:无公开 API、登录墙 + 签名风控、内容多为图片/自由文,无法稳定自动化;改为**用户截图 → 会话视觉提取 → 标准库校验入库**(§28),同 §22 `import-ai` 的人机协作模式。

## 3. 岗位范围

全部远程岗位,不限职能。

## 4. 核心流程

```
采集(6 个 fetcher,各自独立容错)
  → 归一化(统一 Job 模型,职能类目映射)
  → 去重(源内按 source_id;跨源按 标题+公司 指纹)
  → 入库(SQLite upsert,维护 first_seen_at / last_seen_at)
  → 周报(本周新增岗位,Markdown,中英双语)
```

## 5. 统一 Job 模型

| 字段 | 说明 |
|------|------|
| `source` | 来源渠道标识(remotive / wwr / remoteok / jobicy / himalayas / workingnomads) |
| `source_id` | 源内唯一 ID |
| `title` | 岗位名称 |
| `company` | 公司名 |
| `category` | 归一化职能类目(见 §6) |
| `location_constraint` | 地区限制原文(如 Worldwide、USA Only、Europe) |
| `region` | 归一化地区(worldwide / americas / europe / asia_pacific / africa_middle_east / other) |
| `salary_text` | 薪资原文(可为空) |
| `tags` | 标签列表 |
| `url` | 岗位原始链接(必须保留,周报中直接可点) |
| `published_at` | 源发布时间 |
| `first_seen_at` / `last_seen_at` | 本系统首次/最近抓到时间 |
| `fingerprint` | 跨源去重指纹 = normalize(title) + normalize(company) |

## 6. 职能类目(归一化目标集)

软件开发 / 设计 / 产品 / 数据 / 市场营销 / 销售 / 客户支持 / 运营与人力 / 财务与法务 / 写作 / 其他。
各源自带类目通过映射表转换;无法识别的进「其他」,并在日志中记录以便补充映射(沉淀为测试用例)。

## 7. 产出

- **数据库**:`data/jobs.db`(SQLite),唯一约束 `(source, source_id)`,指纹索引。
- **周报**:`reports/<ISO年>-W<周号>.md`(如 `2026-W28.md`)。
  - 中英双语框架文字。
  - 默认按 **职能** 作为一级目录;支持 `--group-by region` 切换为按地区分组。
  - 每条岗位:标题(链接到原始 URL)、公司、地区限制、薪资(如有)、来源、发布日期。
  - 头部汇总:本周新增数、各源采集状态、累计库存量。

## 8. 技术栈与运行

- Python 3.14,仅标准库 + pytest(不引入第三方运行时依赖,降低维护成本)。
- 入口:`python3 -m remote_jobs run`(采集+入库+出报告)、`report`(仅重新生成报告)、`import-ai --week <周>`(导入速览/面试准备)、`ingest-xhs --week <周>`(导入小红书截图提取的岗位,见 §28)。
- Indeed(§27)/ LinkedIn(§29)邮件源由 `run` 自动采集,共用 `mailbox.toml` 的 QQ 邮箱 IMAP 授权码;未配置则静默跳过。
- 定时:Claude Code scheduled task,每周一上午触发;跑稳后可迁移 launchd。

## 9. 目录结构

```
├── SPEC.md
├── src/remote_jobs/
│   ├── models.py          # Job 数据模型
│   ├── http.py            # HTTP 抓取(超时、UA、重试)
│   ├── fetchers/          # 每源一个模块:fetch()取原始数据 + parse()纯函数解析
│   ├── normalize.py       # 类目/地区映射
│   ├── dedupe.py          # 指纹与跨源去重
│   ├── db.py              # SQLite 存取
│   ├── report.py          # 周报生成
│   └── __main__.py        # CLI
├── tests/
│   ├── fixtures/          # 各源真实 API 响应快照
│   └── test_*.py
├── data/jobs.db
└── reports/
```

## 10. 测试策略(规范②的落地)

1. 每个 fetcher 的 `parse()` 是纯函数,用 `tests/fixtures/` 中的**真实 API 响应快照**做输入断言输出。
2. 归一化、去重、周报生成均为纯函数,直接单测。
3. DB 层用临时文件级 SQLite 测 upsert / first_seen / last_seen 语义。
4. **用例积累规则**:线上每次出现解析失败或类目未识别,必须把该样本裁剪后加入 fixtures 并补测试,先红后绿。
5. `python3 -m pytest` 一键全量回归,任何提交前必须全绿。

## 11. 里程碑

- **M1(已交付 2026-07-11)**:6 源采集 + 入库 + 双语周报 + 全量测试 + 每周定时。首次运行入库 378 条。
- **M2(进行中,2026-07-11 确认)**:关注清单订阅 → 数据质量加固 → 本地浏览网页(见 §12–14)。
- M3(备选):HN Who's Hiring、ATS 定向公司清单。

## 12. M2.1 关注清单订阅

- 配置文件:项目根目录 `watchlist.toml`(stdlib `tomllib` 读取),初始只含注释模板,规则由用户自填。
- 规则字段:`name`(版块标题)、`keywords`(命中标题或 tags,OR,不区分大小写)、`exclude_keywords`(命中即排除)、`categories` / `regions`(归一化 key,限定)、`companies`(公司名子串)。规则内维度 AND、维度内 OR;规则间独立,一条岗位可命中多条规则。
- 周报:命中非空时,在「概览」后插入「🎯 重点关注 | Watchlist Highlights」版块,按规则名分小节;命中岗位仍保留在正文分组。
- CLI:`--watchlist PATH`(默认根目录 `watchlist.toml`);文件缺失或无规则时静默跳过该版块。

## 13. M2.2 数据质量加固

1. 薪资解析:`salary.py` 纯函数 `parse_salary(text) -> (min, max, currency) | None`,覆盖 `$55k - $100k`、`OTE $25k - $35k`、`USD 100,000 - 150,000`、`€60k`、单值等;k 展开为数值,识别 USD/EUR/GBP;解析失败返回 None(周报仍显示原文)。
2. DB 迁移:jobs 表增加 `salary_min / salary_max / salary_currency`;`connect()` 用 `PRAGMA table_info` 检测并 `ALTER TABLE`,老库无损升级。
3. 周报环比:概览行显示 `本周新增 N(上周 M,环比 ±x%)`,双语。
4. 未识别类目汇总:`normalize.UNKNOWN_CATEGORIES` 收集,run 结束打印汇总,按 §10 沉淀映射与用例。
5. 过期清理:`prune --days N`(默认 180)删除 `last_seen_at` 过旧的行并 VACUUM;默认不自动删除。

## 14. M2.3 本地浏览网页

- `python3 run.py web` 从 SQLite 全量导出,渲染纯静态单文件 `web/jobs.html`(岗位 JSON 内嵌 + 原生 JS,无需服务器);`run` 命令每次顺带重新生成。
- 功能:关键词搜索(标题/公司/tags);职能/地区/来源下拉筛选;薪资下限筛选(基于 salary_min);「仅看活跃」(last_seen 14 天内)与「仅看本周新增」开关;中英双语界面;保留原始链接与 Remote OK 出处;深浅色主题适配。
- 安全:岗位数据 JSON 内嵌必须转义 `</script>` 等,防止数据破坏页面结构。

## 15. M3.1 HN Who's Hiring 数据源(2026-07-11 确认)

- 数据获取(Algolia HN Search API,免费无鉴权,两步):
  1. `search_by_date?tags=story,author_whoishiring` 取标题以 "Ask HN: Who is hiring?" 开头的最新帖(月初自动切新帖)。
  2. `search_by_date?tags=comment,story_{id}&hitsPerPage=1000&page=N` 按 `nbPages` 翻页拉全部评论(上限 5 页)。
- 解析规则(宽进严出,解析不出即跳过,不算失败):
  - 只要顶层评论(`parent_id == story_id`),回复丢弃;
  - 首行 = 第一个 `<p>` 前的文本,去标签、`html.unescape`;
  - 首行必须含整词 REMOTE(不区分大小写),Onsite 帖排除;
  - 按 `|` 切分,不足 2 段丢弃;公司 = 段 0,职位 = 段 1;
  - 地区限制 = 段 2+ 中首个含 remote 的段;薪资 = 段 2+ 中首个含货币符号或 `数字k` 的段;
  - `url` 指向 HN 评论直链 `news.ycombinator.com/item?id=...`,`source_id` = 评论 id,tags 附 `HN {YYYY-MM}` 月份标记。
- 注册表排在最末:跨源去重优先级最低,同岗位保留聚合站的结构化版本。
- 月更帖 + 每周采集:同帖重复抓取靠 `(source, source_id)` upsert 幂等,只有新评论进当周周报。

## 16. M3.2 IM 机器人通知(2026-07-11 确认)

- 通道类型(配置在 profile 的 notify.toml,`[[channels]]`;文件缺失或无 channels 时静默跳过):
  1. `feishu`:飞书群自定义机器人 webhook(字段 webhook_url / secret 可选签名);
  2. `wecom`:企业微信**内部群**群机器人 webhook(字段 webhook_url;外部群不支持群机器人);
  3. `wecom_app`(2026-07-12 增加,解决外部群无法加机器人的问题):企业微信自建应用直发个人,字段 corpid / corpsecret / agentid / touser(默认 `@all`,即应用可见范围内全员);发送流程 = gettoken 换 access_token → message/send 发 markdown 应用消息;要求管理后台配置「企业可信IP」为本机出口 IP,IP 变更会报 60020,日志需给出明确提示;corpsecret 等同凭据,只存本地。
- 触发:`run` 命令在周报生成后推送;`notify` 子命令基于当前数据库随时重发(配置验证用)。
- 内容:标题含「远程岗位」关键词(便于机器人设关键词白名单)+ 周号;正文为 5 条亮点岗位 + 统计(本周新增/环比/库存)+ 周报链接。
- 链接指向(2026-07-12 确认):配置了 `[pages] base_url` 时,亮点岗位链接指向**站内详情页**(含中文速览/面试准备/防诈提醒,页内再去原站申请);未配置回退原站链接。周报链接同理(线上 URL / 本地路径文本)。
- 亮点挑选:按关注规则顺序轮转、每轮各取 1 条(组内发布时间新到旧),跨规则去重,封顶 5 条;关注清单无命中时仍发送运行完成通知。
- 可靠性:通知失败只记日志,绝不影响采集与周报;POST 不重试,避免重复推送。飞书 secret 非空时按官方 HMAC-SHA256 算法签名。
- 安全:webhook 视为敏感信息,只存本地 notify.toml,日志不回显完整 URL。

## 17. M4.1 GitHub Pages 发布(2026-07-11 确认)

- `site/` 为独立 git 仓库(项目本身不入 git),只存放生成的静态页面,推送到公开 GitHub 仓;代码、SPEC、watchlist、notify.toml、jobs.db 一律不进该仓。
- `publish` 子命令:从 DB 生成 `site/index.html`(浏览页)、`site/reports/<week>.html`(HTML 周报,与 Markdown 周报同结构,由 report_html.py 直接从数据渲染,不做 Markdown 转换)、`site/reports/index.html`(历史周报列表);随后在 site/ 内 add/commit/push。
- `run` 命令在 `site/.git` 存在时自动 publish;发布失败只记日志,不影响采集/周报/通知。
- notify.toml 顶层 `[pages] base_url` 配置后,IM 通知中的周报行升级为可点击的线上 URL(`<base_url>/reports/<week>.html`),未配置回退本地路径文本。
- 隐私权衡已确认:页面公开(URL 难猜但不加密),求职动向公开可接受。

## 18. M4.2 AI 岗位点评(2026-07-11 确认)

- JD 入库:Job 模型与 jobs 表增加 `description`(截断 5000 字符);7 个源全部补填;浏览网页**不**内嵌描述(体积)。
- picks 协议:`reports/<周>-picks.json` = `[{"source","source_id","score","comment"}]`(score 1–10,comment 一句中文点评)。该文件由每周一定时会话的 Agent 产出,脚本只消费:
  - 周报(Markdown 与 HTML)在「重点关注」前插入「🤖 本周最值得投 | AI Top Picks」版块(按分数降序);
  - IM 通知的亮点区改用 AI Top 5(链接 + ⭐分数 + 点评),picks 缺失时回退轮转挑选;
  - `load_picks` 校验:source_id 必须在库、分数在 1–10,非法条目跳过并告警。
- 打分视角(通用,已确认;根目录存在 profile.md 时定时会话改用个性化视角):薪资透明且有竞争力、公司质量、JD 具体清晰、亚洲时区友好、正式全职优先。
- 定时会话执行顺序:`run --skip-notify` → 查库读本周关注命中岗位的标题+描述 → 打分写 picks.json → `report` → `publish` → `notify`。

## 19. M4.3 多人服务(2026-07-11 确认)

- 目录:`profiles/<名字>/watchlist.toml` + `profiles/<名字>/notify.toml`,每人独立的关注规则与通知通道;采集、数据库、浏览页、AI 精选保持全局一份。
- 回退兼容:`profiles/` 不存在(或其中无有效子目录)时,回退根目录 `watchlist.toml` / `notify.toml`,行为与单人模式完全一致。
- 周报:多于一个 profile 时,「重点关注」版块标题带人名前缀(`kevin · AI / ML`);单 profile 不加前缀。
- 通知:每人只收到自己 watchlist 命中的亮点,发到自己的通道;A 的通道失败不影响 B;`notify --profile 名字` 只重发单人。
- 现有配置迁移为 `profiles/kevin/`。

## 20. M5 分享体验与求职工作台(2026-07-11 确认)

- 浏览页页头增加入口:📰 本周周报、🗂 历史周报、📡 RSS(仅 site 版传入相对链接;本地 web/jobs.html 保持无链接的单文件形态)。
- OG 链接预览:浏览页与周报 HTML 输出 `og:title / og:description / og:site_name` 与 `<meta name="description">`,分享到 IM 时显示卡片;描述带动态数据(岗位总数/本周新增)。
- RSS:`site/feed.xml`(RSS 2.0),item 为本周新增岗位(发布时间新到旧,封顶 100),guid=岗位原链接,pubDate 用 RFC-822;所有文本经 XML 转义。
- 公开仓 README:`site/README.md`,含简介、三入口绝对链接(base_url)、RSS 地址与 auto-generated 声明。
- 求职工作台(纯前端,localStorage,按浏览器隔离):每条岗位可标记 ⭐感兴趣 / 📮已投递 / 🙈忽略,键为 `job-status:<source>:<source_id>`;筛选栏增加状态下拉(全部/感兴趣/已投递/忽略/未标记);默认视图隐藏「忽略」;计数行显示标记统计。

## 21. M6 岗位详情页与可分享筛选(2026-07-11 确认)

- **详情页**:`site/jobs/{source}-{sha1(source:source_id)[:16]}.html`,仅为活跃岗位(last_seen 60 天内)生成,每次发布**全量重建**该目录(过期页面自动消失);内容:标题/公司/元信息、净化后的完整 JD、「去原站申请」按钮、返回链接、每页独立 OG 卡片。
- **JD 净化**(渲染进我们域名前必须过白名单):保留 p/br/ul/ol/li/strong/b/em/i/u/blockquote/code/pre/h*(降级 h3/h4)/a(仅 http(s) href,强制 nofollow noopener);script/style/iframe/object/embed/form/svg/noscript 连内容剥除;其余标签剥壳留内容;属性全部丢弃(仅白名单 href);截断输入必须输出配平 HTML;纯文本按空行分段。
- **可能已关闭**:last_seen 距页面生成时间超 7 天,详情页顶部显示标注。
- **AI 徽章**:本周 picks 命中的岗位,浏览页列表与详情页显示 ⭐分数(详情页附点评)。
- **浏览页接线**:payload 每条岗位附 `detail`(仅活跃岗位;本地 web/jobs.html 不附)与 `ai_score`;有 detail 时标题指向详情页、meta 行加「↗ 原链接」。
- **描述截断**:DESCRIPTION_LIMIT 5000 → 15000。
- **可分享筛选**:筛选状态(q/category/region/source/salary/status/active/fresh)以 URLSearchParams 序列化进 `location.hash`,加载时还原;复制地址栏 URL 即分享当前视图。

## 22. M7 时区筛选、AI 速览/面试准备、sitemap/PWA(2026-07-12 确认)

- **时区推断**(`timezones.infer_range`,保守策略,没把握返回 None):
  - 显式写法:`UTC+3` / `GMT-5` / `UTC -1 to UTC+3`(范围)→ 直接取值;
  - 缩写白名单:PST/PT→-8、MST→-7、EST/ET→-5、CET→+1、CEST→+2、BST→+1、JST→+9、AEST→+10、SGT→+8,命中取锚点 ±3;**CST/IST 因歧义不识别**;
  - Himalayas 的 `timezoneRestrictions` 数字列表为源提供值(`tz_source="source"`),其余源文本推断(`tz_source="inferred"`),在 collect 阶段统一补全。
- **时区 UI**(2026-07-12 放宽):浏览页勾选「时区可协作(UTC+8±3)」,通过 = tz 区间与 [UTC+5, UTC+11] 有交集,或无时区信息且 region=worldwide(宽松兜底);勾选时计数行显示「部分时区来自 JD 推断」提醒;详情页时区行推断值标注「(推断)」。
- **筛选措辞**(2026-07-12):地区下拉明确为「👤 所在地要求 | Candidate location」——表达岗位对求职者所在地区的要求,并带悬停说明。
- **防诈免责声明**(2026-07-12,全站固定要素,共享常量 `report.DISCLAIMER`):浏览页 footer、详情页「去原站申请」按钮上方、周报(Markdown 与 HTML)页脚、公开仓 README 四处统一展示:本站仅自动聚合公开信息、不对真实性负责、凡要求缴费垫资均为骗局。

## 23. M8 周报交互化与「清晨海岸」主题(2026-07-12 确认)

- **共享主题** `theme.py`:全站唯一 CSS 来源(浏览页/周报 HTML/详情页),「清晨海岸」设计令牌——浅色暖沙底 `#faf7f2` + 白卡片,深色 `#0c1418` + `#122029`;主渐变 teal→sky(浅 `#0d9488→#0284c7`,深 `#2dd4bf→#38bdf8`);圆角悬浮卡片、pill chips、渐变按钮、hero 标语「Work from anywhere 🌴 自由工作,生活在别处」。
- **周报 HTML 交互**(Markdown 周报保持纯文本不变):
  - 岗位标题链接指向站内详情页 `../jobs/<hash>.html`(本周新增必有详情页),行内保留「↗ 原链接」;
  - 「重点关注」渲染为顶部 chips(规则名+命中数),单版块显示,默认第一个;
  - 岗位列表渲染为职能 chips(含「全部」+数量)过滤;
  - 两个列表均为单一 `<ul>` + `li[data-*]` 属性过滤(不复制 DOM),每页 50 条,pager = 上一页/下一页 + 页码下拉;切换 chips 回第 1 页。
- **浏览页分页**:移除 500 条上限,每页 50 条 + pager;筛选变化回第 1 页;页码以 `p` 参与 hash 分享。

## 24. M10 电鸭社区接入、跨周去重、来源筛选移除(2026-07-12 确认)

- **电鸭接入**(SOURCE="eleduck"):列表 `category=5&sort=-published_at` 拉 1–4 页,**客户端**过滤必须同时含 tag 8(企业直招)与 tag 19(全职远程),剔除 closed/hide/deleted/付费置顶;合格帖(封顶 40)逐个拉详情取 JD 全文,请求间隔 0.3s。
- **公司名启发式**(帖子无结构化公司字段):标题开头『【X】/「X」/[X]』→ 否则按 `｜/|/—/-` 切分首段(≤16 字且不含招聘类词才采纳)→ 兜底 `电鸭直招帖`。
- **固定映射**:region=asia_pacific(中文社区);location_constraint="全职远程(电鸭·中文社区)";salary_text 留空(中文月薪 "15-25k" 会被年薪解析器误判,v1 不提数字);category 由职业 tag 映射(开发/产品/设计/运营/其它)。
- **跨周去重(全源生效)**:新 `(source, source_id)` 入库前查指纹——库中存在同 fingerprint 且 last_seen 在 **30 天内**的其他岗位 → 视为重发跳过并计数;超 30 天视为新一轮招聘正常入库。`upsert_jobs` 返回 `(inserted, duplicates_skipped)`。
- **浏览页移除「来源」筛选下拉**;岗位行中的来源展示保留。

## 25. M11 V2EX 接入(2026-07-12 确认)

- 两个节点各拉最新 10 帖(`remote` 远程工作、`jobs` 酷工作),按 topic id 合并去重;免登录限流 120 次/时,周采 2 请求。
- 过滤(宽进严出):剔除 deleted;jobs 节点标题必须含整词 `远程|remote`;标题命中求助词(求职/求 offer/请教/应该/怎么/如何/吗/求带/接单)剔除;必须命中招聘信号(招/岗位/职位/工程师/经理/设计师/hiring/engineer/…/薪/数字k)之一。
- 公司名启发式抽为共享模块 `cn_title.py`(电鸭/V2EX 共用,电鸭行为不变);V2EX 增补否决词:内推/relocate/主要城市名/外企/可谈——方括号 `[X]` 在 V2EX 惯例是城市/标记;兜底 `V2EX 招聘帖`。
- 固定映射:region=asia_pacific;location="远程(V2EX·中文社区)";salary 不解析(中文月薪,同电鸭);description=content_rendered;tags 标注来源节点;published_at=created epoch 转 +08:00 ISO。
- 已知边界:老 API 每节点仅最新 10 帖,繁忙周可能漏;产出基线跑两周评估该源去留。

## 26. M12 分享二维码(2026-07-12 确认)

- 浏览页 hero 增加「📱 分享 | Share」按钮,点击弹出面板:二维码(扫码直达线上浏览页)+ 页面 URL 文本;再点关闭。未来社交媒体分享按钮加在同一面板(本期不做,仅留扩展位)。
- 二维码生成:**纯 Python 标准库实现的 QR 编码器**(`qr.py`),发布时把固定 URL 编码为 SVG 内嵌页面——零外部依赖、零运行时 JS 计算。技术参数:byte 模式、纠错级 L、版本 1–5 自动选择(单块 RS,容量 ≤106 字节)、固定掩码 0、静区 4 模块。
- 正确性保障:格式信息 BCH 已知向量断言;结构不变量测试(定位图形/时序线/尺寸);存在 `qrcode` pip 包时与其矩阵逐位对拍(importorskip,可选测试,不引入运行时依赖)。
- 仅站点版页面带二维码(本地 web/jobs.html 无公网 URL,不显示按钮)。
- **job_ai 表**(跨周持久,详情页每周重建所以不能落文件):(source, source_id) 主键,tldr(中文速览)、prep_brief、prep_questions(JSON 数组)、updated_at。
- **导入协议**:定时会话写 `reports/<周>-summaries.json`(关注命中岗位 ≤100,每条 2–3 句中文速览)与 `reports/<周>-prep.json`(AI Top 5,公司速查 + 可能面试题);`run.py import-ai --week <周>` 校验后入库(source_id 必须在库、文本非空,非法跳过)。
- **详情页渲染**:tldr → JD 前「🇨🇳 中文速览(AI 生成)」;prep → 页尾「🎯 面试准备(AI 生成)」(brief 段落 + 问题有序列表);全部纯文本转义,不引入富文本。
- **sitemap/PWA**:base_url 非空时生成 `sitemap.xml`(index + reports + jobs 全部页面);`manifest.webmanifest` + `icon.svg` 支持手机「添加到主屏幕」;浏览页 head 挂 manifest/icon/theme-color。

## 27. M13 Indeed 邮件源(2026-07-15 确认)

- **来源合法性**:不爬 Indeed。Indeed 官方免费求职 API 已停;改为通过 IMAP 读取用户自己 QQ 邮箱里收到的 Indeed「求职提醒 / Job alert」邮件——读的是用户自己的收件箱,合法且稳定。
- **配置文件**:`mailbox.toml`(仓库根,**gitignore,含凭据**;Indeed 与 LinkedIn §29 共用此一份 QQ 邮箱凭据)。字段:`host`(默认 `imap.qq.com`)、`port`(默认 993,SSL)、`user`(QQ 邮箱地址)、`authcode`(**QQ 邮箱 IMAP 授权码,非登录密码**,用户自行在 QQ 邮箱设置生成)、`folder`(默认 `INBOX`)、`since_days`(回溯天数,默认 8,略大于周采周期)。缺文件或缺 `authcode`/`user` 时邮件源静默跳过(0 条),不阻塞整体。共享底座 = `fetchers/_email_source.py`。
- **fetcher `indeed_email`**:发件人 `SENDER = donotreply@jobalert.indeed.com`(**用完整地址**——实测 QQ IMAP 的 `FROM` 搜索匹配完整地址与 `indeed.com`,但不匹配中间子串 `jobalert.indeed.com`)。`fetch()` 委托 `_email_source.fetch_messages(SENDER)`:`imaplib`+SSL 登录 → `SELECT folder` → `SEARCH (FROM sender SINCE date)` → 逐封取 HTML 打包 JSON;IO 与解析分离,`parse()` 只吃 JSON。按发件人精确过滤 = 天然「只读该周期新收到的该源邮件」;旧邮件被重读时 source_id 已在库,upsert 只刷新 last_seen 不计新增。
- **解析 `parse_email_html`(纯函数,可单测)** — 结构已用 2026-07 真实样例校准:标准库 `html.parser`,**以 `<h2>` 内的锚点为标题锚**(比 jk 更稳,且能覆盖赞助岗);每张卡片 token 序列 = 标题 → 公司(纯文本)→ [星级评分] → 地区 → [薪资] → [轻松申请按钮] → JD 摘要 → 发布时间。
  - `source_id`:锚点 `href` 带 `jk=` 用 jk;赞助岗(`/pagead/clk`,无 jk)用 `sha1(title|company)` 前 16 位加 `ad-` 前缀兜底,稳定去重。
  - 公司 = 标题后第 1 段文本;地区 = 之后第一段有意义文本(**跳过纯数字星级评分**如 `3.9`、发布时间、按钮、薪资);JD 摘要 = 地区后最长的一段(清掉偶发 HTML 碎片)。
  - **页脚截断**:命中样板词(`此处显示的是`/`查看所有招聘职位`/`© Indeed Ireland`/`取消订阅`…)即进入页脚,本卡片后续文本全部丢弃,防免责声明/公司地址混入描述。
  - 链接保留 Indeed 追踪跳转原样(可点击有效)。宽进严出:空标题丢弃。
- **归一化**:source=`indeed`;category 由标题映射(`record_unknown=False`,同 HN/V2EX);region 由 location 走 `map_region`,**中文地名(大连市/兰州市等)未命中关键词时默认 `asia_pacific`**(cn.indeed 中国岗位提醒);salary_text 留空(人民币不做数字解析,同电鸭/V2EX);tags=`["Indeed 邮件提醒"]`;published_at 取邮件 Date。
- **注册与优先级**:加入 `ALL_FETCHERS` 末位;Indeed 链接是追踪跳转、结构性弱于聚合站,跨源去重时优先级靠后。
- **归一化补充**:`normalize._REGION_KEYWORDS` 增补中文地区词(全球/中国/北京/上海/深圳/广州/杭州/美国/欧洲/日本/新加坡/远程 等)。
- **校准状态**:2026-07-15 已用真实样例(`inbox/indeed/` 一封 19 岗邮件)校准,并沉淀 `tests/fixtures/indeed_alert_sample.html`(覆盖 jk 岗/评分/赞助岗/页脚);当日实测 IMAP 拉取 9 封、解析 69 岗全部正确归一。
- **测试**:样例 HTML 喂 `parse_email_html`,断言 4 岗、jk/哈希 source_id、评分跳过、页脚不泄漏;缺配置时 `fetch()` 返回空、`parse()` 返回 `[]`。

## 28. M13 小红书半手动 ingest(2026-07-15 确认)

- **为何不自动**:小红书无公开 API、登录墙 + 签名(x-s/x-t)风控、内容多为截图/自由文,定时无人采集不可行且有 ToS 风险。采用人机协作:用户截图 → 会话视觉提取 → 标准库校验入库(同 §22 `import-ai` 精神)。
- **收件夹**:`inbox/xhs/`(仓库根)。用户随时把小红书岗位截图丢入;可选 `notes.md` 补充博主/原文链接/备注。处理完的图归档到 `inbox/xhs/_processed/<周>/`,避免重复读。截图与 `inbox/` 一并 gitignore(含个人内容)。
- **交接文件**:会话读 `inbox/xhs/` 未处理截图,视觉提取岗位,写 `reports/<周>-xhs.json`——数组,每条:`title`(必填)、`company`(必填,提不出用「小红书分享」兜底)、`category`(可选,缺则标题映射)、`location_constraint`(可选,默认「远程(小红书)」)、`region`(可选,默认 `worldwide`)、`salary_text`、`url`(博主/原文链接,如 xhslink)、`blogger`(博主名,入 tags)、`published_at`、`description`。
- **命令 `ingest-xhs --week <周>`**(模块 `xhs_ingest.py`,标准库):读 `reports/<周>-xhs.json`,校验(title/company 非空)→ 归一化为 Job(source=`xhs`;`source_id` = `sha1(title|company)` 前 16 位,稳定,重复 ingest 不产生重复)→ 走现有 upsert 入库,进入去重/周报/发布全流程。非法条目跳过并计数。
- **测试**:合法/非法 JSON 各样例喂 `ingest-xhs`,断言入库条数、source_id 稳定性(同 title+company 两次 ingest 不重复)、缺字段跳过计数、category 自动映射。

## 29. M14 LinkedIn 邮件源(2026-07-15 确认)

- **来源合法性**:不爬 LinkedIn。通过 IMAP 读取用户自己 QQ 邮箱里收到的「LinkedIn Job Alerts」邮件(发件人 `jobalerts-noreply@linkedin.com`)。与 Indeed(§27)**共用同一 QQ 邮箱与 `mailbox.toml` 凭据**,只是发件人不同。
- **共享底座**:IMAP 拉取/配置/正文抽取抽为 `fetchers/_email_source.py`(`load_mailbox_config` / `extract_html` / `email_date_to_iso` / `fetch_messages(sender, source_label)`);`indeed_email` 与 `linkedin_email` 各自只保留 `SENDER` 常量 + 特有解析。原 `indeed.toml` 迁移为共享 `mailbox.toml`。
- **fetcher `linkedin_email`**:`SENDER = jobalerts-noreply@linkedin.com`(完整地址,实测有效)。
- **解析 `parse_email_html`(纯函数)** — 结构已用真实样例校准:标准库 `html.parser`。每张卡片 = 岗位链接(`/jobs/view/<id>`,锚文本即标题;同一岗位链接在邮件里出现约 3 次,按 id 去重)→ 紧跟一行「公司 · 地区 (工作方式)」→ 一行状态(`Actively recruiting`/`N school alum`,忽略)。
  - `source_id` = LinkedIn job id;`url` = 规范链接 `https://www.linkedin.com/jobs/view/<id>/`(去掉一次性 tracking 参数)。
  - 「公司 · 地区」按 `·` 切分;工作方式由 `remote|hybrid|on-?site` 词(括号可有可无)判定。
- **远程过滤(项目聚焦远程)**:只保留工作方式为 **Remote / Hybrid** 的岗位,纯 On-site 或无工作方式标记的丢弃;tags 标注 `["LinkedIn 邮件提醒", "Remote"/"Hybrid"]`。
- **归一化**:source=`linkedin`;category 由标题映射;region 由地区文本走 `map_region`(英文中国城市名 Shanghai/Beijing/… 已补入关键词表,先于 `remote` 兜底命中,故 "Shanghai (Remote)" 判为亚太;中文地名未命中默认亚太);salary_text 空;published_at 取邮件 Date。
- **注册与优先级**:加入 `ALL_FETCHERS` 末位。
- **校准状态**:2026-07-15 已用真实样例(`inbox/linkedin/` 一封)校准;当日实测 IMAP 拉取 18 封、解析 58 个 Remote/Hybrid 岗位。fixture=`tests/fixtures/linkedin_alert_sample.html`(覆盖 Remote/Hybrid 保留、On-site 与无标记丢弃、Remote(Worldwide) 保留)。
- **归一化补充**:`normalize._REGION_KEYWORDS` 补英文中国城市(shanghai/beijing/shenzhen/guangzhou/hangzhou/chengdu/wuhan/nanjing/suzhou/dalian + hong kong/taiwan/taipei)。
- **测试**:样例 HTML 喂 `parse_email_html`,断言只留 Remote/Hybrid、公司/地区/规范 url、跨邮件按 id 去重;缺配置 `fetch()` 返回空。
