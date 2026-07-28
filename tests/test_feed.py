import xml.etree.ElementTree as ET

from remote_jobs.feed import MAX_ITEMS, render_feed
from remote_jobs.models import Job


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="$100k", tags=[], url=f"https://example.com/{source_id}",
                    published_at="2026-07-10T08:00:00+00:00")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


KW = dict(base_url="https://x.github.io/board", week_label="2026-W28",
          generated_at_iso="2026-07-11T04:00:00+00:00")


def test_feed_is_valid_xml_with_items():
    xml = render_feed([make_job("1"), make_job("2", title="Designer")], **KW)
    root = ET.fromstring(xml)
    assert root.tag == "rss"
    items = root.findall("./channel/item")
    assert len(items) == 2
    assert items[0].findtext("title") == "Acme | Backend Engineer"
    assert items[0].findtext("link") == "https://example.com/1"
    assert items[0].findtext("guid") == "remotive:1"
    assert root.findtext("./channel/link") == "https://x.github.io/board"


def test_feed_escapes_special_chars():
    job = make_job(title="C++ & <Rust> Engineer", company='O"Corp')
    xml = render_feed([job], **KW)
    root = ET.fromstring(xml)  # 未转义会直接解析失败
    assert root.find("./channel/item/title").text == 'O"Corp | C++ & <Rust> Engineer'


def test_feed_pubdate_rfc822():
    xml = render_feed([make_job()], **KW)
    pub = ET.fromstring(xml).findtext("./channel/item/pubDate")
    assert "Jul 2026" in pub and pub.endswith(("+0000", "GMT", "-0000")), pub
    assert "Fri" in pub


def test_feed_caps_items_and_sorts_newest_first():
    jobs = [make_job(str(i), published_at=f"2026-07-{(i % 9) + 1:02d}T00:00:00+00:00")
            for i in range(150)]
    root = ET.fromstring(render_feed(jobs, **KW))
    items = root.findall("./channel/item")
    assert len(items) == MAX_ITEMS
    dates = [i.findtext("pubDate") for i in items]
    assert "9 Jul" in dates[0], "最新的排最前"


def test_feed_empty_week_and_bad_dates():
    root = ET.fromstring(render_feed([], **KW))
    assert root.findall("./channel/item") == []
    root = ET.fromstring(render_feed([make_job(published_at="不是日期")], **KW))
    assert root.find("./channel/item/pubDate") is None, "解析不了的日期省略 pubDate"
