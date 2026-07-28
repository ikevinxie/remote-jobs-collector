"""HTTP 抓取:统一 UA、超时与重试。"""
from __future__ import annotations

import logging
import ssl
import time
import urllib.request

logger = logging.getLogger(__name__)

try:
    # macOS 的 python.org 发行版不带系统根证书,优先用 certifi(若已安装)
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover - 取决于运行环境
    _SSL_CONTEXT = ssl.create_default_context()

USER_AGENT = "Mozilla/5.0 (RemoteJobsCollector; personal weekly digest)"
TIMEOUT_SECONDS = 30
RETRIES = 3


def fetch_url(url: str) -> str:
    """GET url 并返回文本;失败重试,最终失败抛出异常由调用方容错。"""
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_SSL_CONTEXT) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as error:  # noqa: BLE001 - 任何网络错误都走重试
            last_error = error
            logger.warning("抓取失败(第 %d/%d 次)%s: %s", attempt, RETRIES, url, error)
            if attempt < RETRIES:
                time.sleep(2 * attempt)
    raise RuntimeError(f"抓取 {url} 连续 {RETRIES} 次失败") from last_error


def post_json(url: str, payload: dict) -> str:
    """POST JSON 并返回响应文本。不重试:通知类请求重试会造成重复推送。"""
    import json

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_SSL_CONTEXT) as response:
        return response.read().decode("utf-8", errors="replace")
