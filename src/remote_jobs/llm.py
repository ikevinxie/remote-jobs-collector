"""百炼 DashScope API 集成：AI 打分 / 速览 / 面试准备 / 小红书截图视觉提取。

替代原本由本地 Claude Code 会话完成的 step 3b / 4b-d，使整条流水线
可以无人值守跑在 GitHub Actions 上。纯标准库实现，跟 AI digest 项目的
collector/llm.py 同一套套路（chat + extract_json + parse-retry），
额外加 chat_vision 用于小红书截图。

环境变量：
  DASHSCOPE_API_KEY  必需，百炼 API key
  DASHSCOPE_MODEL         文本模型，默认 qwen-max
  DASHSCOPE_VISION_MODEL  视觉模型，默认 qwen-vl-max
"""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_MODEL = "qwen-max"
DEFAULT_VISION_MODEL = "qwen-vl-max"
MAX_RETRIES = 2         # 网络/HTTP 错误重试
PARSE_RETRIES = 2       # LLM 返回畸形 JSON 时回喂修正
TIMEOUT = 300
SUMMARY_BATCH = 25      # 速览每批岗位数（每条 2-3 句，token 不大）
PICKS_BATCH = 30        # 打分每批岗位数（要带 JD 摘要，token 较大）

# SSL context：优先 certifi，回退到不校验（GitHub Actions runner 上 certifi 通常有）
try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = ssl.create_default_context()
    try:
        _CTX.check_hostname = False
        _CTX.verify_mode = ssl.CERT_NONE
    except Exception:
        pass

USER_AGENT = "remote-jobs-board/1.0 (+github-actions)"

JSON_SYSTEM_PROMPT = (
    "你是远程工作岗位周报的 AI 编辑。严格按用户要求的 JSON 结构输出，"
    "不要输出任何 JSON 以外的文字。\n"
    "JSON 必须语法合法：所有字符串用双引号、无尾随逗号、无注释、无孤立括号或多余字符；"
    "字符串值内部如需引号请用 \\\" 转义，不要直接换行打断 JSON 结构。")


# ---------------------------------------------------------------------------
# 底层：API key / model / chat / chat_vision / extract_json / retry
# ---------------------------------------------------------------------------

def _api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        raise RuntimeError(
            "缺少 DASHSCOPE_API_KEY 环境变量。\n"
            "  GitHub Actions: 在 Settings → Secrets 中添加\n"
            "  本地: export DASHSCOPE_API_KEY=sk-...")
    return key


def _model() -> str:
    return os.environ.get("DASHSCOPE_MODEL", DEFAULT_MODEL)


def _vision_model() -> str:
    return os.environ.get("DASHSCOPE_VISION_MODEL", DEFAULT_VISION_MODEL)


def _post(payload: dict, *, model: str) -> str:
    """发一次 chat completion 请求，返回 assistant 文本。网络错误自动重试。"""
    key = _api_key()
    payload = {"model": model, **payload}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(1 + MAX_RETRIES):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            req = urllib.request.Request(
                API_URL, data=body, method="POST",
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                })
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, IndexError, OSError) as e:
            last_err = e
    raise RuntimeError(f"百炼 API 调用失败（重试 {MAX_RETRIES} 次）: {last_err}")


def chat(prompt: str, *, system: str = JSON_SYSTEM_PROMPT) -> str:
    """文本对话。system 默认是严格 JSON 输出指令。"""
    return _post({
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }, model=_model())


def chat_vision(image_path: str | Path, prompt: str,
                *, system: str = JSON_SYSTEM_PROMPT) -> str:
    """视觉对话：把本地图片 base64 内联，跟 prompt 一起发给视觉模型。"""
    p = Path(image_path)
    raw = p.read_bytes()
    # 简单嗅探 mime；小红书截图基本都是 png/jpg
    mime = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    return _post({
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ]},
        ],
        "temperature": 0.2,
    }, model=_vision_model())


def extract_json(text: str):
    """从 LLM 回复中提取 JSON。处理 markdown 围栏 / 前后缀文本。

    当文本同时含 `{...}` 和 `[...]` 时（如 `[{"x": 1}]`），优先返回
    **跨度最大**的解析结果，避免错拿内层对象。
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 收集所有可解析的 (span, value)，取跨度最大的
    candidates: list[tuple[int, object]] = []
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                val = json.loads(text[start:end + 1])
                candidates.append((end - start, val))
            except json.JSONDecodeError:
                continue
    if candidates:
        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1]
    raise ValueError(f"无法从 LLM 回复中提取 JSON（前 200 字符: {text[:200]}）")


def _chat_json(prompt: str, *, system: str = JSON_SYSTEM_PROMPT,
               label: str = "call") -> object:
    """chat + extract_json + 解析失败回喂修正。"""
    reply = chat(prompt, system=system)
    last_err: ValueError | None = None
    for attempt in range(PARSE_RETRIES + 1):
        try:
            return extract_json(reply)
        except ValueError as e:
            last_err = e
            if attempt == PARSE_RETRIES:
                break
            print(f"  ⚠ {label} 第 {attempt + 1} 次解析失败，回喂修正：{e}",
                  file=sys.stderr, flush=True)
            fix_prompt = (
                f"你上一次输出无法被 JSON 解析器接受，错误：{e}\n\n"
                f"上一次输出原文：\n{reply}\n\n"
                "请只输出修正后的合法 JSON，不要任何解释、不要 markdown 围栏、"
                "不要前后缀文字。检查：双引号转义、无尾随逗号、无孤立括号、"
                "字符串内不要直接换行。")
            reply = chat(fix_prompt, system=system)
    assert last_err is not None
    raise last_err


def _chat_vision_json(image_path: str | Path, prompt: str,
                      *, system: str = JSON_SYSTEM_PROMPT,
                      label: str = "vision") -> object:
    """chat_vision + extract_json + 解析失败回喂修正。"""
    reply = chat_vision(image_path, prompt, system=system)
    last_err: ValueError | None = None
    for attempt in range(PARSE_RETRIES + 1):
        try:
            return extract_json(reply)
        except ValueError as e:
            last_err = e
            if attempt == PARSE_RETRIES:
                break
            print(f"  ⚠ {label} 第 {attempt + 1} 次解析失败，回喂修正：{e}",
                  file=sys.stderr, flush=True)
            fix_prompt = (
                f"你上一次输出无法被 JSON 解析器接受，错误：{e}\n\n"
                f"上一次输出原文：\n{reply}\n\n"
                "请只输出修正后的合法 JSON 数组，不要任何解释、不要 markdown 围栏。")
            # 视觉修正：再发一次图 + 修正指令
            reply = chat_vision(image_path, fix_prompt, system=system)
    assert last_err is not None
    raise last_err


# ---------------------------------------------------------------------------
# 业务函数：4 个 AI 产出
# ---------------------------------------------------------------------------

_PICKS_SYSTEM = (
    "你是远程工作岗位的资深评审。给每个岗位打 1-10 分，标准（按重要性排序）："
    "(1) 薪资透明且有竞争力；(2) 公司质量（融资/客户/口碑）；(3) JD 具体清晰；"
    "(4) 亚洲时区友好（UTC+8 ± 3 优先）；(5) 正式全职优先于兼职/合同。\n"
    "注意：电鸭/V2EX 等中文源的月薪写法（如 15-25k 人民币/月）不要与美元年薪混淆，"
    "换算成年薪再比较（人民币月薪 × 12 / 7 ≈ 美元年薪粗估）。\n"
    "只输出 JSON 数组，挑分数最高的 5-8 条，按分数降序。")

_SUMMARIES_SYSTEM = (
    "你是远程工作岗位周报的中文编辑。给每个岗位写 2-3 句中文 TL;DR，"
    "覆盖：公司一句话定位 + 岗位核心职责 + 薪资/远程政策亮点。"
    "不要 markdown，不要列表，纯文本一段。只输出 JSON 数组。")

_PREP_SYSTEM = (
    "你是远程岗位面试教练。给每个岗位写：(1) brief：公司速查 2-3 句中文，"
    "覆盖业务/规模/技术栈/文化；(2) questions：5 个可能的面试问题，中文，"
    "结合 JD 技术栈与公司背景，避免泛泛而谈。只输出 JSON 数组。")

_XHS_SYSTEM = (
    "你是小红书截图信息提取助手。从截图里提取所有远程工作岗位，每个岗位一个对象。"
    "字段：title（必填，岗位名）、company（必填，提不出用「小红书分享」兜底）、"
    "category（可选，engineering/design/product/marketing/sales/support/data/other 之一）、"
    "location_constraint（可选，如「远程(亚太)」）、region（可选，worldwide/asia_pacific/"
    "americas/europe 之一）、salary_text（可选，原文照抄）、url（可选，截图里的 xhslink 或原文链接）、"
    "blogger（可选，博主名）、published_at（可选，YYYY-MM-DD，提不出留空）、"
    "description（可选，1-3 句中文岗位描述）。只输出 JSON 数组，没有岗位输出 []。")


def _format_candidates(jobs: list[dict], *, with_desc: bool, desc_limit: int = 600) -> str:
    """把候选岗位格式化成 prompt 里的列表。with_desc=True 时带 JD 摘要。"""
    lines = []
    for j in jobs:
        head = (f"- source={j.get('source')} source_id={j.get('source_id')}\n"
                f"  标题: {j.get('title', '')}\n"
                f"  公司: {j.get('company', '')}\n"
                f"  薪资: {j.get('salary_text') or '未公开'}\n"
                f"  地区: {j.get('location_constraint') or '未注明'} / region={j.get('region') or '?'}")
        if with_desc:
            desc = (j.get("description") or "").strip().replace("\n", " ")
            if len(desc) > desc_limit:
                desc = desc[:desc_limit] + "…"
            head += f"\n  JD 摘要: {desc or '（无）'}"
        lines.append(head)
    return "\n".join(lines)


def score_picks(candidates: list[dict], *, profile_md: str = "") -> list[dict]:
    """对候选打分，返回 picks 数组（已按分数降序，封顶 8 条）。

    candidates 元素需含 source / source_id / title / company / salary_text /
    location_constraint / region / description。profile_md 非空时切换到个性化视角。
    """
    if not candidates:
        return []
    perspective = (
        f"\n\n个性化视角（用户 profile.md）：\n{profile_md.strip()}\n"
        "请优先按此 profile 的偏好打分，而不是通用标准。"
        if profile_md.strip() else ""
    )
    out: list[dict] = []
    batches = [candidates[i:i + PICKS_BATCH]
               for i in range(0, len(candidates), PICKS_BATCH)]
    for idx, batch in enumerate(batches):
        if len(batches) > 1:
            print(f"  打分批次 {idx + 1}/{len(batches)}（{len(batch)} 个候选）…",
                  flush=True)
        prompt = (
            f"下面是 {len(batch)} 个候选远程岗位。按系统提示的标准打分，"
            f"挑分数最高的若干条（每批最多 8 条），按分数降序输出 JSON 数组，"
            f"每条字段：source / source_id / score（1-10 浮点）/ comment（一句中文点评）。\n"
            f"source 与 source_id 必须与下面列表完全一致，不要改。\n\n"
            f"{_format_candidates(batch, with_desc=True)}{perspective}")
        parsed = _chat_json(prompt, system=_PICKS_SYSTEM,
                            label=f"picks 批次 {idx + 1}/{len(batches)}")
        if isinstance(parsed, dict) and "picks" in parsed:
            parsed = parsed["picks"]
        if not isinstance(parsed, list):
            raise ValueError(f"picks 批次 {idx + 1}: 期望 JSON 数组，得到 {type(parsed).__name__}")
        out.extend(parsed)
    # 全局再排一次，封顶 8
    out = [p for p in out if isinstance(p, dict)
           and isinstance(p.get("score"), (int, float))]
    out.sort(key=lambda p: p["score"], reverse=True)
    return out[:8]


def write_summaries(candidates: list[dict]) -> list[dict]:
    """对全部候选写中文 TL;DR，返回 summaries 数组（封顶 100 条）。"""
    if not candidates:
        return []
    candidates = candidates[:100]
    out: list[dict] = []
    batches = [candidates[i:i + SUMMARY_BATCH]
               for i in range(0, len(candidates), SUMMARY_BATCH)]
    for idx, batch in enumerate(batches):
        if len(batches) > 1:
            print(f"  速览批次 {idx + 1}/{len(batches)}（{len(batch)} 个候选）…",
                  flush=True)
        prompt = (
            f"下面是 {len(batch)} 个远程岗位。给每个写 2-3 句中文 TL;DR，"
            f"输出 JSON 数组，每条字段：source / source_id / tldr。\n"
            f"source 与 source_id 必须与下面列表完全一致。\n\n"
            f"{_format_candidates(batch, with_desc=True, desc_limit=400)}")
        parsed = _chat_json(prompt, system=_SUMMARIES_SYSTEM,
                            label=f"summaries 批次 {idx + 1}/{len(batches)}")
        if isinstance(parsed, dict) and "summaries" in parsed:
            parsed = parsed["summaries"]
        if not isinstance(parsed, list):
            raise ValueError(f"summaries 批次 {idx + 1}: 期望数组，得到 {type(parsed).__name__}")
        out.extend(parsed)
    return [s for s in out if isinstance(s, dict) and s.get("tldr")]


def write_prep(picks: list[dict], candidates_by_key: dict[tuple[str, str], dict],
               *, top_n: int = 5) -> list[dict]:
    """对 picks 的 Top N 写面试准备包，返回 prep 数组。

    candidates_by_key: {(source, source_id): job_dict}，用来给 LLM 看 JD。
    """
    top = picks[:top_n]
    if not top:
        return []
    # 把 picks 跟 JD 拼起来
    enriched = []
    for p in top:
        key = (str(p.get("source", "")), str(p.get("source_id", "")))
        job = candidates_by_key.get(key, {})
        enriched.append({**p, **job})
    prompt = (
        f"下面是 {len(enriched)} 个本周 AI 精选岗位（含分数与点评）。"
        f"给每个写面试准备包，输出 JSON 数组，每条字段："
        f"source / source_id / brief（公司速查 2-3 句中文）/ "
        f"questions（5 个面试问题，字符串数组）。\n"
        f"source 与 source_id 必须与下面列表完全一致。\n\n"
        f"{_format_candidates(enriched, with_desc=True, desc_limit=800)}")
    parsed = _chat_json(prompt, system=_PREP_SYSTEM, label="prep")
    if isinstance(parsed, dict) and "prep" in parsed:
        parsed = parsed["prep"]
    if not isinstance(parsed, list):
        raise ValueError(f"prep: 期望数组，得到 {type(parsed).__name__}")
    return [p for p in parsed if isinstance(p, dict)
            and (p.get("brief") or p.get("questions"))]


def extract_xhs_jobs(image_path: str | Path, *, notes: str = "") -> list[dict]:
    """视觉提取一张小红书截图里的岗位，返回 xhs.json 风格的数组。

    notes: 可选，inbox/xhs/notes.md 的内容，作为辅助上下文。
    """
    extra = f"\n\n辅助备注（来自 notes.md，仅供参考）：\n{notes.strip()}" if notes.strip() else ""
    prompt = (
        "请提取这张截图里所有远程工作岗位，输出 JSON 数组，字段见系统提示。"
        "如果截图里没有岗位信息（比如只是封面/广告），输出 []。"
        + extra)
    parsed = _chat_vision_json(image_path, prompt, system=_XHS_SYSTEM,
                               label=f"xhs {Path(image_path).name}")
    if isinstance(parsed, dict) and "jobs" in parsed:
        parsed = parsed["jobs"]
    if not isinstance(parsed, list):
        raise ValueError(f"xhs {Path(image_path).name}: 期望数组，得到 {type(parsed).__name__}")
    # 最低校验：title 必填
    kept = []
    for e in parsed:
        if not isinstance(e, dict):
            continue
        title = str(e.get("title", "")).strip()
        if not title:
            continue
        e["title"] = title
        e.setdefault("company", "小红书分享")
        kept.append(e)
    return kept
