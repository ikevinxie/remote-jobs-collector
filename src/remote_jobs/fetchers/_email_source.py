"""邮件源共享底座(见 SPEC.md §27/§29)。

Indeed 与 LinkedIn 的求职提醒都发到同一个 QQ 邮箱,凭据相同、只是发件人不同。
本模块封装共享的 IMAP 拉取 + 配置读取 + 正文抽取,各源只需提供 SENDER + 解析器。

配置:仓库根 `mailbox.toml`(gitignore,含 IMAP 授权码)。缺文件或缺 authcode
时静默跳过——`fetch_messages()` 返回空载荷。
"""
from __future__ import annotations

import email
import imaplib
import json
import logging
import tomllib
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from pathlib import Path

logger = logging.getLogger(__name__)

# mailbox.toml 在仓库根:本文件 = src/remote_jobs/fetchers/_email_source.py,上溯 3 层
MAILBOX_PATH = Path(__file__).resolve().parents[3] / "mailbox.toml"

_DEFAULTS = {
    "host": "imap.qq.com",
    "port": 993,
    "user": "",
    "authcode": "",
    "folder": "INBOX",
    "since_days": 8,
}


def load_mailbox_config(path: Path = MAILBOX_PATH) -> dict | None:
    """读 mailbox.toml;缺文件或缺 user/authcode 返回 None(未配置,静默跳过)。"""
    if not path.exists():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as error:
        logger.error("mailbox.toml 无法解析,跳过邮件源: %s", error)
        return None
    cfg = {**_DEFAULTS, **{k: v for k, v in raw.items() if k in _DEFAULTS}}
    if not str(cfg["authcode"]).strip() or not str(cfg["user"]).strip():
        logger.info("mailbox.toml 未填 user/authcode,跳过邮件源")
        return None
    return cfg


def extract_html(msg: email.message.Message) -> str:
    """从邮件取 text/html 正文;多部分时优先 html,退回 text/plain。"""
    html_parts: list[str] = []
    text_parts: list[str] = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/html", "text/plain"):
            continue
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
        except (LookupError, ValueError) as error:
            logger.warning("邮件正文解码失败,跳过该部分: %s", error)
            continue
        (html_parts if ctype == "text/html" else text_parts).append(decoded)
    return "\n".join(html_parts) if html_parts else "\n".join(text_parts)


def email_date_to_iso(date_header: str) -> str:
    if not date_header:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(date_header)
        return dt.isoformat() if dt else ""
    except (TypeError, ValueError):
        return ""


def fetch_messages(sender: str, *, source_label: str,
                   config_path: Path = MAILBOX_PATH) -> str:
    """IMAP 拉取近 since_days 天、来自 sender 的邮件,打包为 JSON。未配置返回空载荷。

    只按发件人精确过滤 → 天然做到「只读该周期新收到的该源邮件」;旧邮件即便落在
    时间窗内被重读,其岗位 source_id 已在库,upsert 只刷新 last_seen,不计新增。
    """
    cfg = load_mailbox_config(config_path)
    if cfg is None:
        return json.dumps({"messages": []})

    since = (datetime.now(timezone.utc) - timedelta(days=int(cfg["since_days"]))).strftime("%d-%b-%Y")
    messages: list[dict] = []
    conn = imaplib.IMAP4_SSL(cfg["host"], int(cfg["port"]))
    try:
        conn.login(cfg["user"], cfg["authcode"])
        conn.select(cfg["folder"], readonly=True)
        typ, data = conn.search(None, "FROM", f'"{sender}"', "SINCE", since)
        if typ != "OK":
            raise RuntimeError(f"IMAP SEARCH 失败: {typ}")
        uids = data[0].split() if data and data[0] else []
        logger.info("%s 邮件源:命中 %d 封(发件人含 %s,近 %s 天)",
                    source_label, len(uids), sender, cfg["since_days"])
        for uid in uids:
            typ, msg_data = conn.fetch(uid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            messages.append({
                "msg_id": uid.decode(errors="replace"),
                "date": msg.get("Date", ""),
                "subject": str(make_header(decode_header(msg.get("Subject", "")))),
                "html": extract_html(msg),
            })
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001 - 关闭失败无需影响已取数据
            pass
    return json.dumps({"messages": messages}, ensure_ascii=False)
