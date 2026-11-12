import re
from html.parser import HTMLParser


def text_content(html: str) -> str:
    '''
    collapse an HTML fragment to plain text
    '''
    parser = _TextParser()
    parser.feed(html or "")
    parser.close()
    text = "".join(parser.parts)
    return re.sub(r"\s+", " ", text).replace("…", "").strip()


def leading_blockquote(html: str) -> tuple[str | None, str]:
    '''
    split a leading <blockquote> off an HTML fragment:
    (inner_html, remainder), or (None, original) when there is no leading quote
    '''
    parser = _LeadingBlockquoteParser()
    parser.feed(html or "")
    parser.close()
    if not parser.found or parser.depth:
        return None, html
    return "".join(parser.inner), "".join(parser.after)


class _TextParser(HTMLParser):
    BLOCK_TAGS = {
            "address", "article", "aside", "blockquote", "br", "dd", "div",
            "dl", "dt", "figcaption", "figure", "footer", "h1", "h2", "h3",
            "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p",
            "pre", "section", "table", "td", "th", "tr", "ul",
            }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str):
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs):
        if tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str):
        if tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs):
        if tag in self.BLOCK_TAGS:
            self.parts.append(" ")


class _LeadingBlockquoteParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.found = False
        self.depth = 0
        self.failed = False
        self.inner: list[str] = []
        self.after: list[str] = []
        self._before: list[str] = []

    def _emit(self, raw: str):
        if self.failed:
            return
        if self.depth:
            self.inner.append(raw)
        elif self.found:
            self.after.append(raw)
        else:
            self._before.append(raw)

    def handle_starttag(self, tag: str, attrs):
        raw = self.get_starttag_text()
        if self.failed:
            return
        if not self.found:
            if tag.lower() == "blockquote" and not "".join(self._before).strip():
                self.found = True
                self.depth = 1
            else:
                self.failed = True
            return
        if tag.lower() == "blockquote":
            self.depth += 1
        self._emit(raw)

    def handle_startendtag(self, tag: str, attrs):
        if self.failed:
            return
        if not self.found:
            self.failed = True
            return
        self._emit(self.get_starttag_text())

    def handle_endtag(self, tag: str):
        if self.failed or not self.found:
            return
        if tag.lower() == "blockquote":
            self.depth -= 1
            if self.depth == 0:
                return
        self._emit(f"</{tag}>")

    def handle_data(self, data: str):
        if self.failed:
            return
        if not self.found:
            if data.strip():
                self.failed = True
            else:
                self._before.append(data)
            return
        self._emit(data)

    def handle_entityref(self, name: str):
        self._emit(f"&{name};")

    def handle_charref(self, name: str):
        self._emit(f"&#{name};")

    def handle_comment(self, data: str):
        if self.failed:
            return
        if not self.found:
            self.failed = True
            return
        self._emit(f"<!--{data}-->")

    def handle_decl(self, decl: str):
        if not self.found:
            self.failed = True
            return
        self._emit(f"<!{decl}>")

    def handle_pi(self, data: str):
        if not self.found:
            self.failed = True
            return
        self._emit(f"<?{data}>")

    def unknown_decl(self, data: str):
        if not self.found:
            self.failed = True
            return
        self._emit(f"<![{data}]>")
