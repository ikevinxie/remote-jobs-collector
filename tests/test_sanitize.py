from remote_jobs.sanitize import sanitize_html


def test_keeps_whitelisted_tags():
    out = sanitize_html("<p>Hi <strong>there</strong></p><ul><li>a</li></ul>")
    assert out == "<p>Hi <strong>there</strong></p><ul><li>a</li></ul>"


def test_script_dropped_with_content():
    out = sanitize_html('<p>ok</p><script>alert("xss")</script><p>after</p>')
    assert "alert" not in out and "script" not in out
    assert "<p>ok</p>" in out and "<p>after</p>" in out
    assert "iframe" not in sanitize_html('<iframe src="https://evil.com">内嵌</iframe>')


def test_event_handlers_and_style_attrs_stripped():
    out = sanitize_html('<p onclick="steal()" style="color:red">text</p>')
    assert out == "<p>text</p>"


def test_anchor_href_whitelisting():
    out = sanitize_html('<a href="https://good.com" onclick="x()">link</a>')
    assert out == '<a href="https://good.com" rel="nofollow noopener" target="_blank">link</a>'
    assert sanitize_html('<a href="javascript:alert(1)">bad</a>') == "bad"
    assert sanitize_html('<a href="mailto:a@b.c">mail</a>') == "mail"


def test_unknown_tags_unwrapped_content_kept():
    out = sanitize_html('<div class="x"><span>内容</span><table><tr><td>格</td></tr></table></div>')
    assert out == "内容格"


def test_headings_downgraded():
    assert sanitize_html("<h1>大标题</h1><h6>小标题</h6>") == "<h3>大标题</h3><h4>小标题</h4>"


def test_truncated_input_balanced():
    out = sanitize_html("<p>开头<ul><li>被截断了一半")
    assert out.count("<p>") == out.count("</p>")
    assert out.count("<ul>") == out.count("</ul>")
    assert out.count("<li>") == out.count("</li>")


def test_plain_text_paragraphized():
    out = sanitize_html("第一段\n\n第二段 <脚本>危险&字符")
    assert "<p>第一段</p>" in out
    assert "&lt;脚本&gt;危险&amp;字符" in out


def test_text_escaped_inside_tags():
    out = sanitize_html("<p>a < b & c</p>")
    assert "&amp;" in out


def test_empty_input():
    assert sanitize_html("") == ""
    assert sanitize_html(None) == ""
