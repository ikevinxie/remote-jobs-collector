import json

from remote_jobs.webpage import render_page


def make_row(**kw):
    defaults = dict(source="remotive", source_id="1", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="$100k", tags=["python"], url="https://example.com/job/1",
                    published_at="2026-07-10T00:00:00+00:00", fingerprint="fp",
                    first_seen_at="2026-07-11T00:00:00+00:00", last_seen_at="2026-07-11T00:00:00+00:00",
                    salary_min=100000, salary_max=100000, salary_currency="USD")
    defaults.update(kw)
    return defaults


NOW = "2026-07-11T04:00:00+00:00"


def test_page_embeds_all_jobs_and_links():
    rows = [make_row(source_id="1"), make_row(source_id="2", title="设计师", url="https://example.com/job/2")]
    html = render_page(rows, generated_at_iso=NOW)
    assert "https://example.com/job/1" in html
    assert "https://example.com/job/2" in html
    assert "设计师" in html
    assert NOW in html


def test_script_injection_is_escaped():
    """岗位文本含 </script> 或引号时,不得破坏内嵌 JSON 的 script 标签。"""
    evil = make_row(title='Evil</script><script>alert(1)</script>', company='O"Corp \\backslash')
    html = render_page([evil], generated_at_iso=NOW)
    payload_area = html[html.index("const DATA"):]
    assert "Evil</script>" not in payload_area, "</ 必须转义为 <\\/"
    assert "Evil<\\/script>" in payload_area
    # 页面整体仍然只有模板自带的闭合 script(数据里的都被转义)
    assert html.count("</script>") == 1


def test_embedded_json_roundtrips():
    rows = [make_row(title="Complex \"quotes\" & <tags>", tags=["a", "b"])]
    html = render_page(rows, generated_at_iso=NOW)
    start = html.index("const DATA = ") + len("const DATA = ")
    end = html.index(";\n", start)
    data = json.loads(html[start:end].replace("<\\/", "</"))
    assert data["jobs"][0]["title"] == 'Complex "quotes" & <tags>'
    assert data["generatedAt"] == NOW


def test_controls_and_bilingual_ui_present():
    html = render_page([make_row()], generated_at_iso=NOW)
    for control_id in ('id="search"', 'id="category"', 'id="region"',
                       'id="salary"', 'id="active"', 'id="fresh"'):
        assert control_id in html
    assert 'id="source"' not in html, "来源筛选下拉已移除(M10)"
    assert '$("source")' not in html, "JS 中无来源筛选分支"
    assert "来源 ${esc(DATA.sources[job.source]" in html, "岗位行仍显示来源"
    assert "全球远程岗位 | Global Remote Jobs" in html
    assert "仅活跃 | Active only" in html
    assert 'href="https://remoteok.com"' in html, "保留 Remote OK 出处"
    assert "prefers-color-scheme: dark" in html


def test_report_links_rendered_only_when_given():
    html = render_page([make_row()], generated_at_iso=NOW,
                       report_links=[("📰 本周周报 | This week", "reports/2026-W28.html"),
                                     ("📡 RSS", "feed.xml")])
    assert '<a href="reports/2026-W28.html">📰 本周周报 | This week</a>' in html
    assert '<a href="feed.xml">📡 RSS</a>' in html
    plain = render_page([make_row()], generated_at_iso=NOW)
    assert 'class="nav"' not in plain, "本地版不带入口链接"


def test_og_meta_and_rss_link():
    html = render_page([make_row()], generated_at_iso=NOW,
                       og={"title": "全球远程岗位", "description": "570 个岗位 & \"每周更新\""},
                       rss_href="feed.xml")
    assert '<meta property="og:title" content="全球远程岗位">' in html
    assert "570 个岗位 &amp; &quot;每周更新&quot;" in html, "og 内容必须转义"
    assert '<link rel="alternate" type="application/rss+xml"' in html
    plain = render_page([make_row()], generated_at_iso=NOW)
    assert "og:title" not in plain


def test_workbench_controls_present():
    html = render_page([make_row()], generated_at_iso=NOW)
    assert 'id="status"' in html, "状态筛选下拉"
    assert 'data-job-key=' in html, "岗位行状态选择器(JS 模板)"
    assert '"job-status:"' in html, "localStorage 键前缀"
    assert 'value="interested"' in html and 'value="applied"' in html and 'value="ignored"' in html
    assert "已投递 | Applied" in html


def test_detail_and_ai_score_reach_payload_and_js_handles_them():
    row = make_row()
    row["detail"] = "jobs/remotive-abc.html"
    row["ai_score"] = "9.5"
    html = render_page([row], generated_at_iso=NOW)
    assert "jobs/remotive-abc.html" in html, "detail 字段进入内嵌数据"
    assert '"ai_score": "9.5"' in html or '"ai_score":"9.5"' in html
    assert "job.detail" in html, "JS 有详情链接分支"
    assert "原链接 | Source" in html
    assert "job.ai_score" in html, "JS 有 AI 徽章分支"


def test_shareable_hash_filter_js_present():
    html = render_page([make_row()], generated_at_iso=NOW)
    assert "applyHashFilters" in html and "updateHash" in html
    assert "URLSearchParams(location.hash.slice(1))" in html
    assert "history.replaceState" in html


def test_timezone_filter_control_and_logic():
    row = make_row()
    row.update(tz_min=5, tz_max=11, tz_source="inferred")
    html = render_page([row], generated_at_iso=NOW)
    assert 'id="tz8"' in html, "时区筛选勾选框"
    assert "时区可协作(UTC+8±3)" in html
    assert '"tz_min": 5' in html or '"tz_min":5' in html, "tz 字段进 payload"
    assert "job.tz_max >= 5 && job.tz_min <= 11" in html, "与 UTC+8±3 区间求交集"
    assert 'job.region === "worldwide"' in html, "无时区信息时全球岗宽松放行"
    assert "tz8" in html.split("FILTER_IDS")[1][:200], "tz8 参与 hash 分享"


def test_timezone_inference_note_bound_to_checkbox():
    html = render_page([make_row()], generated_at_iso=NOW)
    assert "部分岗位时区来自 JD 文本推断" in html
    note_pos = html.index("部分岗位时区来自")
    assert '$("tz8").checked' in html[note_pos - 200:note_pos], "提醒由 tz8 勾选状态控制"


def test_region_filter_labeled_as_candidate_location():
    html = render_page([make_row()], generated_at_iso=NOW)
    assert "👤 所在地要求:不限 | Candidate location: Any" in html
    assert "岗位对求职者所在地区的要求" in html, "悬停说明"


def test_disclaimer_in_footer():
    html = render_page([make_row()], generated_at_iso=NOW)
    assert "请仔细甄别招聘信息真假" in html
    assert "never pay to apply" in html


def test_pwa_extra_head():
    html = render_page([make_row()], generated_at_iso=NOW,
                       extra_head='<link rel="manifest" href="manifest.webmanifest">')
    assert '<link rel="manifest" href="manifest.webmanifest">' in html
    assert "manifest" not in render_page([make_row()], generated_at_iso=NOW), "本地版不带 PWA 头"


def test_pagination_and_hero():
    html = render_page([make_row()], generated_at_iso=NOW)
    assert 'id="pager"' in html
    assert "const PAGE_SIZE = 50" in html
    assert "仅显示前 500 条" not in html, "旧的 500 条上限已移除"
    assert 'params.set("p", String(page))' in html, "页码参与 hash 分享"
    assert "page = 1; updateHash(); render();" in html, "筛选变化回到第 1 页"
    assert "Work from anywhere 🌴" in html, "hero 标语"
    assert "--grad" in html, "清晨海岸主题变量"


def test_share_panel_only_when_qr_given():
    from remote_jobs.qr import qr_svg
    svg = qr_svg("https://x.github.io/board/")
    html = render_page([make_row()], generated_at_iso=NOW,
                       share_qr_svg=svg, share_url="https://x.github.io/board/")
    assert 'id="share-btn"' in html and ">Share</button>" in html
    assert "share-fab" in html, "右下角浮动悬钮(M12.2,避免手机端遮挡 hero 标题)"
    assert "share-corner" not in html
    assert "📱 分享" not in html, "按钮文案纯英文(M12.1)"
    assert 'id="share-panel"' in html and "扫码打开本站" in html
    assert svg in html, "QR SVG 内嵌"
    assert "https://x.github.io/board/" in html
    plain = render_page([make_row()], generated_at_iso=NOW)
    assert 'id="share-btn"' not in plain, "本地版无公网 URL,不显示分享按钮"
    assert "share-panel" in plain.split("<script>")[1], "JS 分支存在但按钮元素守卫"


def test_empty_database_renders():
    html = render_page([], generated_at_iso=NOW)
    assert '"jobs": []' in html or '"jobs":[]' in html
