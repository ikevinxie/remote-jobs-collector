# 自动收集全球的远程工作岗位

每周自动从 9 个免费公开渠道采集全球远程岗位(6 个聚合站/API + HN Who's Hiring 月度帖 +
电鸭社区、V2EX 中文岗位),去重入库 SQLite,生成中英双语 Markdown 周报。

V2EX 源说明:取「远程工作」节点全部 + 「酷工作」节点标题含远程的帖,剔除求助讨论帖;
老 API 每节点仅返回最新 10 帖,繁忙周可能有遗漏。

电鸭源说明:只收「企业直招 + 全职远程」标签的帖子;帖子无结构化公司字段,公司名靠
标题启发式提取,提不出统一记「电鸭直招帖」。跨周重发的同岗位(30 天窗口内同标题+公司
指纹,任意来源)自动拦截不重复入库。

HN 源说明:每月一帖、每周增量采集(靠 upsert 幂等,只有新评论进当周周报),
只收「顶层评论 + 首行标明 REMOTE + `公司 | 职位 | ...` 格式」的帖子,解析不出的直接跳过。
规格说明见 [SPEC.md](SPEC.md);协作规范:先 Spec 后开发,所有产出必须积累测试用例。

## 使用

```bash
python3 run.py run                    # 采集 + 入库 + 生成本周周报 + 更新浏览页面
python3 run.py report                 # 不抓取,仅从数据库重新生成周报
python3 run.py report --group-by region   # 按地区分组
python3 run.py run --days 14          # 周报覆盖最近 14 天新增
python3 run.py web                    # 仅重新生成本地浏览页面 web/jobs.html
python3 run.py prune --days 180       # 清理超过 180 天未再见到的岗位
python3 run.py notify                 # 基于当前数据库重发一次 IM 通知(验证配置用)
python3 run.py import-ai --week 2026-W28   # 导入定时会话产出的中文速览/面试准备
```

- 数据库:`data/jobs.db`
- 周报:`reports/<ISO年>-W<周号>.md`(如 `reports/2026-W28.md`)
- 浏览页面:`web/jobs.html`(本地)/ https://ikevinxie.github.io/remote-jobs-board/(线上),
  支持搜索、按职能/地区/来源/薪资/求职状态筛选;每条岗位可标记 ⭐感兴趣 / 📮已投递 / 🙈忽略
  (存浏览器 localStorage,每人自己生效,忽略的岗位默认隐藏)
- 岗位详情页(仅线上):点击岗位标题查看完整 JD(白名单净化渲染)+「去原站申请」;
  超 7 天未在来源出现会标注「可能已关闭」;AI 精选岗位带 ⭐分数徽章;每页可单独分享(带 OG 卡片)
- 可分享筛选:筛选条件实时写入地址栏 `#hash`,复制 URL 发给别人即还原当前视图
- RSS 订阅:https://ikevinxie.github.io/remote-jobs-board/feed.xml(本周新增岗位)

## 关注清单与多人服务

每人一个目录:`profiles/<名字>/watchlist.toml`(关注规则)+ `profiles/<名字>/notify.toml`(通知通道)。
命中的岗位进入周报「🎯 重点关注」版块(多人时版块标题带人名),并只推送到本人的通道。
给家人朋友加订阅 = 新建一个 `profiles/<名字>/` 目录照模板填两份配置。
关键词按整词匹配(`llm` 不会命中 `installments`);`profiles/` 缺失时回退根目录同名文件(单人模式)。

## AI 岗位点评 / 中文速览 / 面试准备

每周一的定时会话会通读关注命中岗位的 JD:
- **打分**(通用视角:薪资透明、公司质量、JD 清晰、亚洲时区友好、正式全职)→ `reports/<周>-picks.json`,周报与 IM 通知展示「🤖 本周最值得投」;
- **中文速览**(每岗 2–3 句 TL;DR)与 **面试准备**(Top 5 的公司速查 + 可能面试题)→ `import-ai` 入库,显示在岗位详情页,跨周持久。

在根目录放一份 `profile.md`(个人背景)可升级为个性化打分。

## 时区筛选

Himalayas 源自带时区要求;其余源从 JD 保守推断(`UTC+3`、`PST` 等显式写法才认,
CST/IST 因歧义不识别)。浏览页勾「🕐 与东八区可重叠」筛选;详情页显示时区行,推断值带「(推断)」标注。

## 发布上线(GitHub Pages)

`site/` 是独立 git 仓库,只存生成的静态页面(代码/配置/webhook/数据库不上传)。
一次性初始化(需要 GitHub 授权,可让 Claude 代跑,只有 `gh auth login` 要本人操作):

```bash
brew install gh && gh auth login
gh repo create remote-jobs-board --public --clone=false
git init site && git -C site remote add origin "git@github.com:<用户名>/remote-jobs-board.git"
python3 run.py publish        # 生成页面并推送
gh api -X POST "repos/<用户名>/remote-jobs-board/pages" -f 'source[branch]=main' -f 'source[path]=/'
```

之后每次 `run` 自动重新发布;`notify.toml` 里配置 `[pages] base_url` 后,
IM 通知中的周报会变成可点击的线上链接。site/ 未初始化时发布静默跳过。

## IM 通知(飞书 / 企业微信)

编辑 `profiles/<名字>/notify.toml`(内含创建机器人的步骤说明),填入群机器人 webhook 后,
每次 `run` 自动推送:AI 精选(或关注亮点)5 条 + 本周统计;配置 `[pages] base_url` 后
周报链接可直接点击。未配置时静默跳过;通知失败只记日志,不影响采集与周报。

## 测试

```bash
python3 -m pytest -q
```

fixtures 为各源真实 API 响应快照(`tests/fixtures/`)。线上遇到解析失败或未识别类目时,
必须把样本沉淀为新 fixture/测试(先红后绿),见 SPEC.md §10。

## 定时

Claude Code 定时任务 `weekly-remote-jobs-collect`,每周一 09:00 触发
(应用未开启时顺延到下次启动补跑)。

## 依赖

Python 3.14 标准库 + pytest;macOS 上若系统证书缺失会自动使用 certifi(可选)。
