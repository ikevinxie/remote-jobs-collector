"""多人 profile:每人独立的 watchlist 与通知配置(见 SPEC.md §19)。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Profile:
    name: str  # 空串表示根目录回退的单人模式(周报版块不加人名前缀)
    watchlist_path: Path
    notify_path: Path


def load_profiles(profiles_dir: Path, fallback_watchlist: str | Path,
                  fallback_notify: str | Path) -> list[Profile]:
    """扫描 profiles/ 子目录;无有效 profile 时回退根目录配置(单人模式)。"""
    if profiles_dir.is_dir():
        found = [
            Profile(sub.name, sub / "watchlist.toml", sub / "notify.toml")
            for sub in sorted(profiles_dir.iterdir())
            if sub.is_dir() and ((sub / "watchlist.toml").exists() or (sub / "notify.toml").exists())
        ]
        if found:
            return found
        logger.warning("profiles/ 存在但没有任何有效 profile,回退根目录配置")
    return [Profile("", Path(fallback_watchlist), Path(fallback_notify))]
