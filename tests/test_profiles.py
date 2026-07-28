import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from remote_jobs import __main__ as cli
from remote_jobs import db
from remote_jobs.models import Job
from remote_jobs.profiles import load_profiles

# notify 命令内部用真实 datetime.now() 算"本周"窗口,首见时间必须相对当下取值,
# 不能写死日历日期——否则随真实时钟推移会漂出 7 天窗口导致偶发失败。
FRESH_FIRST_SEEN = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="", tags=[], url=f"https://example.com/{source_id}",
                    published_at="2026-07-10T00:00:00+00:00", description="JD")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


def _write_profile(root: Path, name: str, categories: list[str]):
    d = root / name
    d.mkdir(parents=True)
    d.joinpath("watchlist.toml").write_text(
        f'[[rules]]\nname = "{name} 关注"\ncategories = {json.dumps(categories)}\n', encoding="utf-8")
    d.joinpath("notify.toml").write_text(
        '[[channels]]\nprovider = "wecom"\n'
        f'webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={name}"\n', encoding="utf-8")


def test_load_profiles_fallback_to_root(tmp_path):
    profiles = load_profiles(tmp_path / "nope", tmp_path / "w.toml", tmp_path / "n.toml")
    assert len(profiles) == 1
    assert profiles[0].name == "", "回退单人模式,无人名前缀"


def test_load_profiles_discovers_subdirs(tmp_path):
    _write_profile(tmp_path / "profiles", "alice", ["design"])
    _write_profile(tmp_path / "profiles", "kevin", ["engineering"])
    (tmp_path / "profiles" / "无配置的目录").mkdir()
    profiles = load_profiles(tmp_path / "profiles", "w", "n")
    assert [p.name for p in profiles] == ["alice", "kevin"], "无配置文件的目录被忽略"


def test_load_profiles_empty_dir_falls_back(tmp_path):
    (tmp_path / "profiles").mkdir()
    profiles = load_profiles(tmp_path / "profiles", tmp_path / "w.toml", tmp_path / "n.toml")
    assert [p.name for p in profiles] == [""]


def test_project_profiles_are_valid():
    """项目实际配置:profiles/ 下每个 profile 的 watchlist 必须可解析且字段合法。"""
    from remote_jobs.normalize import CATEGORIES, REGIONS
    from remote_jobs.watchlist import load_watchlist
    profiles = load_profiles(cli.ROOT / "profiles", cli.ROOT / "watchlist.toml", cli.ROOT / "notify.toml")
    assert any(p.name == "kevin" for p in profiles), "kevin 已迁移到 profiles/"
    for profile in profiles:
        for rule in load_watchlist(profile.watchlist_path):
            assert rule.name
            assert all(c in CATEGORIES for c in rule.categories)
            assert all(r in REGIONS for r in rule.regions)


def _run_notify(tmp_path, monkeypatch, extra_args=()):
    """跑 notify 子命令,拦截 notify_all,返回 [(profile标签, 亮点岗位ids, 通道keys)]。"""
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("e1"), make_job("d1", title="UI Designer", category="design")],
                   FRESH_FIRST_SEEN)
    conn.close()
    _write_profile(tmp_path / "profiles", "alice", ["design"])
    _write_profile(tmp_path / "profiles", "kevin", ["engineering"])

    calls = []

    def fake_notify_all(channels, highlights, stats, week_label, report_path,
                        report_url="", ai_picks=None, base_url=""):
        calls.append(([c.webhook_url for c in channels], [j.source_id for j in highlights]))
        return {c.provider: True for c in channels}

    monkeypatch.setattr(cli, "notify_all", fake_notify_all)
    code = cli.main(["notify", "--db", str(tmp_path / "jobs.db"),
                     "--reports-dir", str(tmp_path / "reports"),
                     "--profiles-dir", str(tmp_path / "profiles"), *extra_args])
    return code, calls


def test_notify_isolated_per_profile(tmp_path, monkeypatch):
    code, calls = _run_notify(tmp_path, monkeypatch)
    assert code == 0
    assert len(calls) == 2
    by_key = {channels[0]: ids for channels, ids in calls}
    assert by_key["https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=alice"] == ["d1"], "alice 只收设计岗"
    assert by_key["https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=kevin"] == ["e1"], "kevin 只收工程岗"


def test_notify_single_profile_filter(tmp_path, monkeypatch):
    code, calls = _run_notify(tmp_path, monkeypatch, ("--profile", "alice"))
    assert code == 0
    assert len(calls) == 1 and calls[0][1] == ["d1"]


def test_notify_unknown_profile_errors(tmp_path, monkeypatch):
    code, calls = _run_notify(tmp_path, monkeypatch, ("--profile", "bob"))
    assert code == 1 and calls == []
