"""JD HTML 白名单净化(见 SPEC.md §21)。

各源返回的岗位描述是任意 HTML,渲染进我们域名前必须净化:
只保留排版类标签,属性一律丢弃(仅白名单化的 a href),script 等危险容器连内容剥除。
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

# 原样保留(小写)
_KEEP = {"p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "u",
         "blockquote", "code", "pre", "a", "h3", "h4"}
# 标题统一降级,避免破坏页面层级
_HEADING_MAP = {"h1": "h3", "h2": "h3", "h3": "h3", "h4": "h4", "h5": "h4", "h6": "h4"}
# 连内容一起丢弃
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "form", "svg", "noscript"}
_VOID = {"br"}


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open_stack: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            self.drop_depth += 1
            return
        if self.drop_depth:
            return
        tag = _HEADING_MAP.get(tag, tag)
        if tag not in _KEEP:
            return  # 剥壳留内容
        if tag in _VOID:
            self.out.append("<br>")
            return
        if tag == "a":
            href = next((v for k, v in attrs if k.lower() == "href"), "") or ""
            if not href.lower().startswith(("http://", "https://")):
                return  # 非 http(s) 链接剥壳
            self.out.append(f'<a href="{html.escape(href, quote=True)}" rel="nofollow noopener" target="_blank">')
        else:
            self.out.append(f"<{tag}>")
        self.open_stack.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            self.drop_depth = max(0, self.drop_depth - 1)
            return
        if self.drop_depth:
            return
        tag = _HEADING_MAP.get(tag, tag)
        if tag not in _KEEP or tag in _VOID:
            return
        if tag in self.open_stack:
            # 闭合到该标签为止,保持输出配平
            while self.open_stack:
                top = self.open_stack.pop()
                self.out.append(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data):
        if not self.drop_depth and data:
            self.out.append(html.escape(data))

    def close_remaining(self) -> None:
        while self.open_stack:
            self.out.append(f"</{self.open_stack.pop()}>")


def sanitize_html(raw: str) -> str:
    """净化任意来源的 HTML;纯文本输入按空行分段包 <p>。"""
    text = raw or ""
    # 只有出现真正的标签形态(<字母 / </ / <!)才走 HTML 解析,"a < b" 或中文尖括号按纯文本处理
    if not re.search(r"<[a-zA-Z/!]", text):
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
        return "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    parser = _Sanitizer()
    parser.feed(text)
    parser.close()
    parser.close_remaining()
    return "".join(parser.out).strip()
