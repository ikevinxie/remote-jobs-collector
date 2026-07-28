"""llm.py 单测：mock 掉 chat / chat_vision，验证业务函数的解析、批处理、retry。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from remote_jobs import llm


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_object(self):
        assert llm.extract_json('{"a": 1}') == {"a": 1}

    def test_plain_array(self):
        assert llm.extract_json('[1, 2, 3]') == [1, 2, 3]

    def test_markdown_fence(self):
        text = '一些前缀\n```json\n{"a": 1}\n```\n一些后缀'
        assert llm.extract_json(text) == {"a": 1}

    def test_prefix_suffix_noise(self):
        text = '好的，结果如下：\n[{"x": 1}]\n希望对你有帮助。'
        assert llm.extract_json(text) == [{"x": 1}]

    def test_unrecoverable_raises(self):
        with pytest.raises(ValueError, match="无法从 LLM 回复中提取 JSON"):
            llm.extract_json("这根本不是 JSON 也没有括号")


# ---------------------------------------------------------------------------
# _chat_json retry on malformed JSON
# ---------------------------------------------------------------------------

class TestChatJsonRetry:
    def test_retries_then_succeeds(self):
        # 第一次返回畸形 JSON，第二次返回合法 JSON
        replies = ['[{"id": 1, "score": )', '[{"id": 1, "score": 8}]']
        with mock.patch("remote_jobs.llm.chat", side_effect=replies) as m:
            out = llm._chat_json("prompt", label="test")
        assert out == [{"id": 1, "score": 8}]
        assert m.call_count == 2

    def test_raises_after_retries_exhausted(self):
        replies = ["not json"] * (llm.PARSE_RETRIES + 1)
        with mock.patch("remote_jobs.llm.chat", side_effect=replies) as m, \
             pytest.raises(ValueError, match="无法从 LLM 回复中提取 JSON"):
            llm._chat_json("prompt", label="test")
        assert m.call_count == llm.PARSE_RETRIES + 1


# ---------------------------------------------------------------------------
# score_picks
# ---------------------------------------------------------------------------

def _cand(sid: str, **kw) -> dict:
    base = dict(source="hn", source_id=sid, title=f"T{sid}", company=f"C{sid}",
                salary_text="", location_constraint="Worldwide", region="worldwide",
                description="JD text")
    base.update(kw)
    return base


class TestScorePicks:
    def test_empty_candidates_returns_empty(self):
        # 不应调用 LLM
        with mock.patch("remote_jobs.llm.chat") as m:
            assert llm.score_picks([]) == []
        m.assert_not_called()

    def test_single_batch_sorted_and_capped(self):
        cands = [_cand(str(i)) for i in range(3)]
        # LLM 返回乱序，score_picks 应全局排序并封顶 8
        fake = [
            {"source": "hn", "source_id": "2", "score": 9.0, "comment": "best"},
            {"source": "hn", "source_id": "0", "score": 7.0, "comment": "ok"},
            {"source": "hn", "source_id": "1", "score": 8.5, "comment": "good"},
        ]
        with mock.patch("remote_jobs.llm.chat", return_value=json.dumps(fake)):
            picks = llm.score_picks(cands)
        assert [p["source_id"] for p in picks] == ["2", "1", "0"]

    def test_drops_entries_with_invalid_score(self):
        cands = [_cand("0"), _cand("1")]
        fake = [
            {"source": "hn", "source_id": "0", "score": 8, "comment": "ok"},
            {"source": "hn", "source_id": "1", "score": "high", "comment": "bad"},  # 非法
            {"source": "hn", "source_id": "0", "score": 11, "comment": "out of range"},  # 仍保留,校验在 load_picks
        ]
        with mock.patch("remote_jobs.llm.chat", return_value=json.dumps(fake)):
            picks = llm.score_picks(cands)
        # "high" 被丢；11 是数字,这里不卡(load_picks 才卡 1-10)
        assert [p["source_id"] for p in picks] == ["0", "0"]

    def test_multi_batch_merged_and_sorted(self):
        # 超过 PICKS_BATCH 触发分批
        cands = [_cand(str(i)) for i in range(llm.PICKS_BATCH + 5)]
        # 第一批返回 2 条,第二批返回 1 条
        batch1 = [{"source": "hn", "source_id": "0", "score": 7, "comment": "a"},
                  {"source": "hn", "source_id": "1", "score": 9, "comment": "b"}]
        batch2 = [{"source": "hn", "source_id": "30", "score": 8, "comment": "c"}]
        with mock.patch("remote_jobs.llm.chat",
                        side_effect=[json.dumps(batch1), json.dumps(batch2)]):
            picks = llm.score_picks(cands)
        assert [p["source_id"] for p in picks] == ["1", "30", "0"]

    def test_profile_md_injected_into_prompt(self):
        cands = [_cand("0")]
        with mock.patch("remote_jobs.llm.chat",
                        return_value=json.dumps([{"source": "hn", "source_id": "0",
                                                  "score": 8, "comment": "x"}])) as m:
            llm.score_picks(cands, profile_md="偏好: 不要销售岗")
        # 第二次调用（如果有 retry）才会看 prompt；这里只一次
        prompt = m.call_args.kwargs.get("prompt") or m.call_args.args[0]
        assert "偏好: 不要销售岗" in prompt


# ---------------------------------------------------------------------------
# write_summaries
# ---------------------------------------------------------------------------

class TestWriteSummaries:
    def test_empty(self):
        with mock.patch("remote_jobs.llm.chat") as m:
            assert llm.write_summaries([]) == []
        m.assert_not_called()

    def test_drops_entries_without_tldr(self):
        cands = [_cand("0"), _cand("1")]
        fake = [
            {"source": "hn", "source_id": "0", "tldr": "中文速览 0"},
            {"source": "hn", "source_id": "1", "tldr": ""},  # 空,丢
            {"source": "hn", "source_id": "1"},              # 缺字段,丢
        ]
        with mock.patch("remote_jobs.llm.chat", return_value=json.dumps(fake)):
            out = llm.write_summaries(cands)
        assert [s["source_id"] for s in out] == ["0"]

    def test_caps_at_100_candidates(self):
        cands = [_cand(str(i)) for i in range(150)]
        with mock.patch("remote_jobs.llm.chat", return_value="[]") as m:
            llm.write_summaries(cands)
        # 150 截到 100,按 SUMMARY_BATCH=25 分 4 批
        assert m.call_count == 4


# ---------------------------------------------------------------------------
# write_prep
# ---------------------------------------------------------------------------

class TestWritePrep:
    def test_empty_picks(self):
        with mock.patch("remote_jobs.llm.chat") as m:
            assert llm.write_prep([], {}) == []
        m.assert_not_called()

    def test_top_n_limit(self):
        picks = [{"source": "hn", "source_id": str(i), "score": 9 - i, "comment": "c"}
                 for i in range(7)]
        by_key = {("hn", str(i)): _cand(str(i)) for i in range(7)}
        # mock 模拟 LLM 老老实实只回 top 5 的 prep
        fake = [{"source": "hn", "source_id": str(i),
                 "brief": f"brief {i}", "questions": [f"q{j}" for j in range(5)]}
                for i in range(5)]
        with mock.patch("remote_jobs.llm.chat", return_value=json.dumps(fake)) as m:
            out = llm.write_prep(picks, by_key, top_n=5)
        # prompt 里只应包含 top 5 的 JD
        prompt = m.call_args.kwargs.get("prompt") or m.call_args.args[0]
        assert "source_id=0" in prompt
        assert "source_id=4" in prompt
        assert "source_id=5" not in prompt
        assert "source_id=6" not in prompt
        assert len(out) == 5


# ---------------------------------------------------------------------------
# extract_xhs_jobs (vision)
# ---------------------------------------------------------------------------

class TestExtractXhsJobs:
    def test_empty_inbox_image_returns_empty(self, tmp_path):
        # 1x1 png
        img = tmp_path / "x.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        with mock.patch("remote_jobs.llm.chat_vision", return_value="[]"):
            assert llm.extract_xhs_jobs(img) == []

    def test_drops_entries_without_title(self, tmp_path):
        img = tmp_path / "x.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
        fake = [
            {"title": "Backend Engineer", "company": "Acme"},
            {"title": "", "company": "X"},          # 空 title,丢
            {"company": "Y"},                        # 缺 title,丢
            {"title": "Designer"},                   # 缺 company,兜底「小红书分享」
        ]
        with mock.patch("remote_jobs.llm.chat_vision", return_value=json.dumps(fake)):
            out = llm.extract_xhs_jobs(img)
        assert [e["title"] for e in out] == ["Backend Engineer", "Designer"]
        assert out[1]["company"] == "小红书分享"

    def test_notes_passed_to_prompt(self, tmp_path):
        img = tmp_path / "x.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        with mock.patch("remote_jobs.llm.chat_vision", return_value="[]") as m:
            llm.extract_xhs_jobs(img, notes="博主: 小羚不卷\n链接: xhslink.com/abc")
        # chat_vision 第二个位置参数是 prompt
        prompt = m.call_args.args[1]
        assert "小羚不卷" in prompt
        assert "xhslink.com/abc" in prompt


# ---------------------------------------------------------------------------
# 模块级常量 / 默认参数
# ---------------------------------------------------------------------------

def test_json_system_prompt_is_str_not_callable():
    # 回归锁死:之前误把 _JSON_SYSTEM_PROMPT 写成函数,默认参数在 def 时
    # 求值会 NameError。改成模块级字符串常量后,chat / chat_vision 的默认
    # system 必须是非空字符串。
    assert isinstance(llm.JSON_SYSTEM_PROMPT, str)
    assert llm.JSON_SYSTEM_PROMPT.strip()
    import inspect
    chat_system_default = inspect.signature(llm.chat).parameters["system"].default
    assert chat_system_default is llm.JSON_SYSTEM_PROMPT
