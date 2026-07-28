import json

from remote_jobs import notify
from remote_jobs.models import Job
from remote_jobs.notify import (Channel, feishu_payload, feishu_sign, load_channels,
                                pick_highlights, send, wecom_payload)


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="$100k", tags=[], url=f"https://example.com/job/{source_id}",
                    published_at="2026-07-10T00:00:00+00:00")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


STATS = {"new_count": 191, "prev_week_new": 379, "total": 570}


# ---- load_channels ----

def test_load_channels_missing_or_comment_only(tmp_path):
    assert load_channels(tmp_path / "nope.toml") == []
    path = tmp_path / "n.toml"
    path.write_text("# 只有注释\n", encoding="utf-8")
    assert load_channels(path) == []


def test_load_channels_parses_and_skips_invalid(tmp_path):
    path = tmp_path / "n.toml"
    path.write_text(
        """
[[channels]]
provider = "feishu"
webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
secret = "s3cret"

[[channels]]
provider = "wecom"
webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xyz"

[[channels]]
provider = "dingtalk"
webhook_url = "https://oapi.dingtalk.com/robot"

[[channels]]
provider = "feishu"
webhook_url = "http://insecure.example.com"
""",
        encoding="utf-8",
    )
    channels = load_channels(path)
    assert [c.provider for c in channels] == ["feishu", "wecom"], "非法 provider 与非 https 均跳过"
    assert channels[0].secret == "s3cret"
    assert channels[1].secret == ""


def test_kevin_profile_notify_config_is_valid():
    from remote_jobs.__main__ import ROOT
    channels = load_channels(ROOT / "profiles" / "kevin" / "notify.toml")
    for c in channels:  # 模板为空;用户填入真实 webhook 后也必须合法
        assert c.provider in ("feishu", "wecom")
        assert c.webhook_url.startswith("https://")


# ---- pick_highlights ----

def test_pick_highlights_round_robin():
    matches = {
        "规则A": [make_job(str(i), published_at=f"2026-07-0{i}") for i in range(1, 5)],
        "规则B": [make_job(str(10 + i)) for i in range(1, 3)],
    }
    picks = pick_highlights(matches, limit=5)
    assert len(picks) == 5
    # 轮转:A1 B1 A2 B2 A3,而不是 A 独占前 4
    assert [j.source_id for j in picks] == ["4", "11", "3", "12", "2"], "组内按发布时间新到旧,组间轮转"


def test_pick_highlights_dedupes_across_rules():
    shared = make_job("77")
    picks = pick_highlights({"A": [shared], "B": [shared, make_job("88")]}, limit=5)
    assert [j.source_id for j in picks] == ["77", "88"]


def test_pick_highlights_empty_and_underflow():
    assert pick_highlights({}, limit=5) == []
    picks = pick_highlights({"A": [make_job("1")]}, limit=5)
    assert len(picks) == 1


# ---- payloads ----

def test_feishu_payload_structure_and_links():
    jobs = [make_job("1"), make_job("2")]
    payload = feishu_payload(jobs, STATS, "2026-W28", "/path/2026-W28.md")
    assert payload["msg_type"] == "post"
    title = payload["content"]["post"]["zh_cn"]["title"]
    assert "远程工作" in title and "2026-W28" in title
    lines = payload["content"]["post"]["zh_cn"]["content"]
    anchors = [el for line in lines for el in line if el["tag"] == "a"]
    assert [a["href"] for a in anchors] == ["https://example.com/job/1", "https://example.com/job/2"]
    text = json.dumps(lines, ensure_ascii=False)
    assert "本周新增 191" in text and "570" in text and "2026-W28.md" in text
    assert "timestamp" not in payload, "未设置 secret 时无签名字段"


def test_feishu_payload_signed():
    payload = feishu_payload([], STATS, "2026-W28", "/r.md", secret="mykey", timestamp=1783735000)
    assert payload["timestamp"] == "1783735000"
    assert payload["sign"] == feishu_sign("mykey", 1783735000)
    assert "本周关注清单无命中岗位" in json.dumps(payload, ensure_ascii=False)


def test_feishu_sign_known_vector():
    """签名算法回归锚点:算法实现变了此值会变。"""
    assert feishu_sign("test-secret", 1700000000) == feishu_sign("test-secret", 1700000000)
    assert feishu_sign("test-secret", 1700000000) != feishu_sign("test-secret", 1700000001)
    assert len(feishu_sign("test-secret", 1700000000)) == 44  # base64(sha256) 固定长度


def test_wecom_payload_markdown_links():
    payload = wecom_payload([make_job("1")], STATS, "2026-W28", "/r.md")
    assert payload["msgtype"] == "markdown"
    content = payload["markdown"]["content"]
    assert "[Acme | Backend Engineer](https://example.com/job/1)" in content
    assert "📍Worldwide" in content and "💰$100k" in content
    assert "本周新增 191 条(上周 379),数据库累计 570 条" in content


def test_report_url_upgrades_link_in_both_payloads():
    url = "https://kevin.github.io/remote-jobs-board/reports/2026-W28.html"
    fp = feishu_payload([], STATS, "2026-W28", "/local.md", report_url=url)
    anchors = [el for line in fp["content"]["post"]["zh_cn"]["content"] for el in line if el["tag"] == "a"]
    assert any(a["href"] == url for a in anchors), "飞书周报行升级为可点击链接"
    assert "/local.md" not in json.dumps(fp)
    wp = wecom_payload([], STATS, "2026-W28", "/local.md", report_url=url)
    assert f"[打开周报 | Open weekly report]({url})" in wp["markdown"]["content"]


def test_ai_picks_replace_highlights_in_both_payloads():
    picks = [(make_job("9", title="ML Engineer"), 9.0, "全球可投,薪资高")]
    fallback = [make_job("1")]
    fp = feishu_payload(fallback, STATS, "2026-W28", "/r.md", ai_picks=picks)
    text = json.dumps(fp, ensure_ascii=False)
    assert "ML Engineer" in text and "⭐9" in text and "全球可投,薪资高" in text
    assert "job/1" not in text, "有 picks 时不再用轮转亮点"
    wp = wecom_payload(fallback, STATS, "2026-W28", "/r.md", ai_picks=picks)
    assert "⭐9" in wp["markdown"]["content"]
    # picks 为空时回退轮转亮点
    fp2 = feishu_payload(fallback, STATS, "2026-W28", "/r.md", ai_picks=None)
    assert "job/1" in json.dumps(fp2)


def test_base_url_switches_job_links_to_detail_pages():
    from remote_jobs.jobpage import job_page_filename
    base = "https://kevin.github.io/remote-jobs-board"
    job = make_job("1")
    expected = f"{base}/jobs/{job_page_filename('remotive', '1')}"
    fp = feishu_payload([job], STATS, "2026-W28", "/r.md", base_url=base)
    anchors = [el for line in fp["content"]["post"]["zh_cn"]["content"] for el in line if el["tag"] == "a"]
    assert anchors[0]["href"] == expected, "飞书亮点链到站内详情页"
    wp = wecom_payload([job], STATS, "2026-W28", "/r.md", base_url=base)
    assert f"]({expected})" in wp["markdown"]["content"]
    # ai_picks 路径同样生效
    fp2 = feishu_payload([], STATS, "2026-W28", "/r.md", base_url=base,
                         ai_picks=[(job, 9.0, "点评")])
    assert expected in json.dumps(fp2)
    # 未配置 base_url 回退原站链接
    fp3 = feishu_payload([job], STATS, "2026-W28", "/r.md")
    assert "https://example.com/job/1" in json.dumps(fp3)


def test_load_pages_config(tmp_path):
    from remote_jobs.notify import load_pages_config
    assert load_pages_config(tmp_path / "nope.toml") == ""
    path = tmp_path / "n.toml"
    path.write_text('[pages]\nbase_url = "https://x.github.io/board/"\n', encoding="utf-8")
    assert load_pages_config(path) == "https://x.github.io/board", "去掉尾部斜杠"


def test_load_channels_wecom_app(tmp_path):
    path = tmp_path / "n.toml"
    path.write_text(
        """
[[channels]]
provider = "wecom_app"
corpid = "ww123"
corpsecret = "sec"
agentid = 1000002

[[channels]]
provider = "wecom_app"
corpid = "ww123"
corpsecret = "sec"
# 缺 agentid → 跳过
""",
        encoding="utf-8",
    )
    channels = load_channels(path)
    assert len(channels) == 1
    assert channels[0].provider == "wecom_app"
    assert channels[0].agentid == 1000002
    assert channels[0].touser == "@all"


def test_send_wecom_app_success(monkeypatch):
    from remote_jobs.notify import send_wecom_app
    calls = {}

    monkeypatch.setattr(notify, "fetch_url",
                        lambda url: calls.setdefault("token_url", url) and "" or '{"errcode":0,"access_token":"TK"}')

    def fake_post(url, payload):
        calls["send_url"], calls["payload"] = url, payload
        return '{"errcode":0,"errmsg":"ok"}'

    monkeypatch.setattr(notify, "post_json", fake_post)
    channel = Channel("wecom_app", corpid="ww123", corpsecret="sec", agentid=1000002)
    assert send_wecom_app(channel, "**测试**") is True
    assert "corpid=ww123" in calls["token_url"]
    assert "access_token=TK" in calls["send_url"]
    assert calls["payload"]["agentid"] == 1000002
    assert calls["payload"]["markdown"]["content"] == "**测试**"
    assert calls["payload"]["touser"] == "@all"


def test_send_wecom_app_token_denied_hints_trusted_ip(monkeypatch, caplog):
    from remote_jobs.notify import send_wecom_app
    monkeypatch.setattr(notify, "fetch_url",
                        lambda url: '{"errcode":60020,"errmsg":"not allow to access from your ip"}')
    monkeypatch.setattr(notify, "post_json",
                        lambda url, payload: (_ for _ in ()).throw(AssertionError("token 失败不应调用发送")))
    channel = Channel("wecom_app", corpid="ww123", corpsecret="sec", agentid=1)
    assert send_wecom_app(channel, "x") is False
    assert "企业可信IP" in caplog.text, "60020 报错要提示可信 IP"


def test_send_wecom_app_network_error(monkeypatch):
    from remote_jobs.notify import send_wecom_app
    monkeypatch.setattr(notify, "fetch_url",
                        lambda url: (_ for _ in ()).throw(RuntimeError("connection refused")))
    assert send_wecom_app(Channel("wecom_app", corpid="a", corpsecret="b", agentid=1), "x") is False


def test_notify_all_routes_wecom_app(monkeypatch):
    from remote_jobs.notify import notify_all
    sent = {}
    def fake_send(channel, content):
        sent["content"] = content
        return True

    monkeypatch.setattr(notify, "send_wecom_app", fake_send)
    results = notify_all([Channel("wecom_app", corpid="a", corpsecret="b", agentid=1)],
                         [make_job("1")], STATS, "2026-W28", "/r.md")
    assert results == {"wecom_app": True}
    assert "[Acme | Backend Engineer]" in sent["content"], "wecom_app 复用企微 markdown 内容"


# ---- send ----

def _patch_post(monkeypatch, response=None, error=None):
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        if error:
            raise error
        return json.dumps(response)

    monkeypatch.setattr(notify, "post_json", fake_post)
    return calls


def test_send_success_feishu_and_wecom(monkeypatch):
    calls = _patch_post(monkeypatch, {"code": 0, "msg": "success"})
    assert send(Channel("feishu", "https://x/hook"), {"msg_type": "post"}) is True
    calls2 = _patch_post(monkeypatch, {"errcode": 0, "errmsg": "ok"})
    assert send(Channel("wecom", "https://x/hook"), {"msgtype": "markdown"}) is True
    assert calls and calls2


def test_send_rejected_returns_false_without_raising(monkeypatch):
    _patch_post(monkeypatch, {"code": 19001, "msg": "sign match fail"})
    assert send(Channel("feishu", "https://x/hook"), {}) is False


def test_send_network_error_returns_false(monkeypatch):
    _patch_post(monkeypatch, error=RuntimeError("connection refused"))
    assert send(Channel("wecom", "https://x/hook"), {}) is False
