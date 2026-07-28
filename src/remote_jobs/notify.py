"""IM 机器人通知:飞书 / 企业微信群 webhook(见 SPEC.md §16)。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .http import fetch_url, post_json
from .jobpage import job_page_filename
from .models import Job

logger = logging.getLogger(__name__)

PROVIDERS = ("feishu", "wecom", "wecom_app")
HIGHLIGHT_LIMIT = 5


@dataclass
class Channel:
    provider: str
    webhook_url: str = ""
    secret: str = ""
    # wecom_app(企业微信自建应用直发)专用
    corpid: str = ""
    corpsecret: str = ""
    agentid: int = 0
    touser: str = "@all"


def load_channels(path: str | Path) -> list[Channel]:
    """读取通知通道;文件缺失或无 channels 返回空表(通知静默跳过)。"""
    path = Path(path)
    if not path.exists():
        return []
    with path.open("rb") as f:
        data = tomllib.load(f)
    channels: list[Channel] = []
    for raw in data.get("channels", []):
        provider = str(raw.get("provider", "")).strip().lower()
        if provider == "wecom_app":
            corpid = str(raw.get("corpid", "")).strip()
            corpsecret = str(raw.get("corpsecret", "")).strip()
            agentid = raw.get("agentid", 0)
            if not (corpid and corpsecret and isinstance(agentid, int) and agentid > 0):
                logger.warning("wecom_app 通道缺少 corpid/corpsecret/agentid,已跳过")
                continue
            channels.append(Channel(provider=provider, corpid=corpid, corpsecret=corpsecret,
                                    agentid=agentid, touser=str(raw.get("touser", "@all")) or "@all"))
            continue
        url = str(raw.get("webhook_url", "")).strip()
        if provider not in ("feishu", "wecom") or not url.startswith("https://"):
            logger.warning("notify 通道配置非法,已跳过: provider=%r", provider)
            continue
        channels.append(Channel(provider=provider, webhook_url=url, secret=str(raw.get("secret", ""))))
    return channels


def load_pages_config(path: str | Path) -> str:
    """读取 [pages] base_url(用于把通知里的周报路径升级为线上链接);未配置返回空串。"""
    path = Path(path)
    if not path.exists():
        return ""
    with path.open("rb") as f:
        data = tomllib.load(f)
    return str(data.get("pages", {}).get("base_url", "")).rstrip("/")


def pick_highlights(watchlist_matches: dict[str, list[Job]], limit: int = HIGHLIGHT_LIMIT) -> list[Job]:
    """按规则顺序轮转取岗(每轮各规则 1 条,组内发布时间新到旧),跨规则去重,封顶 limit。"""
    queues = [sorted(jobs, key=lambda j: j.published_at, reverse=True) for jobs in watchlist_matches.values()]
    seen: set[tuple[str, str]] = set()
    highlights: list[Job] = []
    round_index = 0
    while len(highlights) < limit and any(round_index < len(q) for q in queues):
        for queue in queues:
            if round_index < len(queue):
                job = queue[round_index]
                key = (job.source, job.source_id)
                if key not in seen:
                    seen.add(key)
                    highlights.append(job)
                    if len(highlights) >= limit:
                        break
        round_index += 1
    return highlights


def _job_link(job: Job, base_url: str) -> str:
    """配置了站点 base_url 时链到站内详情页(含中文速览/面试准备/防诈提醒),否则回退原站。"""
    if base_url:
        return f"{base_url}/jobs/{job_page_filename(job.source, job.source_id)}"
    return job.url


def _job_suffix(job: Job) -> str:
    parts = []
    if job.location_constraint:
        parts.append(f"📍{job.location_constraint}")
    if job.salary_text:
        parts.append(f"💰{job.salary_text}")
    return (" · " + " · ".join(parts)) if parts else ""


def _stats_line(stats: dict) -> str:
    line = f"本周新增 {stats['new_count']} 条"
    if stats.get("prev_week_new") is not None:
        line += f"(上周 {stats['prev_week_new']})"
    line += f",数据库累计 {stats['total']} 条"
    return line


def feishu_sign(secret: str, timestamp: int) -> str:
    """飞书官方算法:以 "{timestamp}\\n{secret}" 为 HMAC 密钥、空消息体做 SHA256 再 base64。"""
    key = f"{timestamp}\n{secret}".encode()
    return base64.b64encode(hmac.new(key, b"", digestmod=hashlib.sha256).digest()).decode()


def feishu_payload(highlights: list[Job], stats: dict, week_label: str, report_path: str,
                   *, secret: str = "", timestamp: int | None = None, report_url: str = "",
                   ai_picks: list[tuple[Job, float, str]] | None = None,
                   base_url: str = "") -> dict:
    lines: list[list[dict]] = []
    if ai_picks:
        lines.append([{"tag": "text", "text": "🤖 本周最值得投:"}])
        for job, score, comment in ai_picks[:HIGHLIGHT_LIMIT]:
            lines.append([
                {"tag": "a", "text": f"{job.company} | {job.title}", "href": _job_link(job, base_url)},
                {"tag": "text", "text": f" ⭐{score:g}" + (f" · {comment}" if comment else "")},
            ])
    elif highlights:
        for job in highlights:
            lines.append([
                {"tag": "a", "text": f"{job.company} | {job.title}", "href": _job_link(job, base_url)},
                {"tag": "text", "text": _job_suffix(job)},
            ])
    else:
        lines.append([{"tag": "text", "text": "本周关注清单无命中岗位。"}])
    lines.append([{"tag": "text", "text": f"📊 {_stats_line(stats)}"}])
    if report_url:
        lines.append([{"tag": "text", "text": "📄 "},
                      {"tag": "a", "text": "打开周报 | Open weekly report", "href": report_url}])
    else:
        lines.append([{"tag": "text", "text": f"📄 周报:{report_path}"}])

    payload: dict = {
        "msg_type": "post",
        "content": {"post": {"zh_cn": {"title": f"🌍 远程工作周报 {week_label}", "content": lines}}},
    }
    if secret:
        ts = timestamp if timestamp is not None else int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = feishu_sign(secret, ts)
    return payload


def wecom_payload(highlights: list[Job], stats: dict, week_label: str, report_path: str,
                  *, report_url: str = "",
                  ai_picks: list[tuple[Job, float, str]] | None = None,
                  base_url: str = "") -> dict:
    lines = [f"## 🌍 远程岗位周报 {week_label}"]
    if ai_picks:
        lines.append("🤖 本周最值得投:")
        lines += [
            f"- [{job.company} | {job.title}]({_job_link(job, base_url)}) ⭐{score:g}"
            + (f" · {comment}" if comment else "")
            for job, score, comment in ai_picks[:HIGHLIGHT_LIMIT]
        ]
    elif highlights:
        lines += [f"- [{job.company} | {job.title}]({_job_link(job, base_url)}){_job_suffix(job)}"
                  for job in highlights]
    else:
        lines.append("本周关注清单无命中岗位。")
    lines.append(f"> 📊 {_stats_line(stats)}")
    if report_url:
        lines.append(f"> 📄 [打开周报 | Open weekly report]({report_url})")
    else:
        lines.append(f"> 📄 周报:{report_path}")
    return {"msgtype": "markdown", "markdown": {"content": "\n".join(lines)}}


def _masked(url: str) -> str:
    return url[:45] + "..." if len(url) > 45 else url


def send(channel: Channel, payload: dict) -> bool:
    """发送并校验响应;任何失败只记日志返回 False,绝不抛异常影响主流程。"""
    try:
        response = json.loads(post_json(channel.webhook_url, payload))
        code = response.get("code", response.get("errcode", -1))
        if code == 0:
            logger.info("通知已发送: %s(%s)", channel.provider, _masked(channel.webhook_url))
            return True
        logger.error("通知被拒绝: %s code=%s msg=%s", channel.provider, code,
                     response.get("msg") or response.get("errmsg"))
        return False
    except Exception as error:  # noqa: BLE001 - 通知失败不能影响采集主流程
        logger.error("通知发送失败: %s: %s", channel.provider, error)
        return False


def send_wecom_app(channel: Channel, markdown_content: str) -> bool:
    """企业微信自建应用直发:gettoken 换 access_token → message/send 发 markdown 应用消息。"""
    try:
        token_response = json.loads(fetch_url(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            f"?corpid={channel.corpid}&corpsecret={channel.corpsecret}"
        ))
        if token_response.get("errcode"):
            hint = ""
            if token_response["errcode"] == 60020:
                hint = "(60020 = 本机出口 IP 不在应用的「企业可信IP」列表,IP 可能变了,去管理后台更新)"
            logger.error("wecom_app 获取 token 失败: %s %s%s",
                         token_response.get("errcode"), token_response.get("errmsg"), hint)
            return False
        response = json.loads(post_json(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token_response['access_token']}",
            {"touser": channel.touser, "msgtype": "markdown",
             "agentid": channel.agentid, "markdown": {"content": markdown_content}},
        ))
        if response.get("errcode") == 0:
            logger.info("通知已发送: wecom_app(agentid=%s)", channel.agentid)
            return True
        hint = "(60020 = 本机出口 IP 不在「企业可信IP」列表)" if response.get("errcode") == 60020 else ""
        logger.error("wecom_app 发送被拒: %s %s%s", response.get("errcode"), response.get("errmsg"), hint)
        return False
    except Exception as error:  # noqa: BLE001 - 通知失败不能影响采集主流程
        logger.error("wecom_app 发送失败: %s", error)
        return False


def notify_all(channels: list[Channel], highlights: list[Job], stats: dict,
               week_label: str, report_path: str, report_url: str = "",
               ai_picks: list[tuple[Job, float, str]] | None = None,
               base_url: str = "") -> dict[str, bool]:
    """逐通道构建并发送,返回 {provider: 是否成功}。"""
    results: dict[str, bool] = {}
    for channel in channels:
        if channel.provider == "feishu":
            payload = feishu_payload(highlights, stats, week_label, report_path,
                                     secret=channel.secret, report_url=report_url,
                                     ai_picks=ai_picks, base_url=base_url)
            results[channel.provider] = send(channel, payload)
        elif channel.provider == "wecom_app":
            payload = wecom_payload(highlights, stats, week_label, report_path,
                                    report_url=report_url, ai_picks=ai_picks, base_url=base_url)
            results[channel.provider] = send_wecom_app(channel, payload["markdown"]["content"])
        else:
            payload = wecom_payload(highlights, stats, week_label, report_path,
                                    report_url=report_url, ai_picks=ai_picks, base_url=base_url)
            results[channel.provider] = send(channel, payload)
    return results
