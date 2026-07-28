"""去重:源内按 (source, source_id),跨源按 title+company 指纹。"""
from __future__ import annotations

from .models import Job


def dedupe(jobs: list[Job]) -> list[Job]:
    """输入顺序即优先级:同一岗位保留最先出现的那条。"""
    seen_ids: set[tuple[str, str]] = set()
    seen_fingerprints: set[str] = set()
    result: list[Job] = []
    for job in jobs:
        key = (job.source, job.source_id)
        if key in seen_ids or job.fingerprint in seen_fingerprints:
            continue
        seen_ids.add(key)
        seen_fingerprints.add(job.fingerprint)
        result.append(job)
    return result
