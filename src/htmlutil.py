import re
from collections.abc import Callable
from html.parser import HTMLParser

URL_ATTRIBUTES = {"href", "poster", "src", "srcset"}
ATTRIBUTE_RE = re.compile(
        r'(?i)(\b(?:href|poster|src|srcset)\s*=\s*)(["\'])(.*?)\2',
        re.DOTALL,
        )


def rewrite_urls(html: str, callback: Callable[[str, str], str | None]) -> str:
    '''
    rewrite URLs in href/src/poster/srcset attributes, leaving other text alone.
    callback receives (url, attribute); returning None removes the attribute
    (or just that srcset candidate).
    '''
    parser = _UrlRewriteParser(callback)
    parser.feed(html or "")
    parser.close()
    return "".join(parser.parts)


def absolutize_html(html: str, origin: str) -> str:
    '''
    make root-relative URLs in an HTML fragment absolute
    '''
    origin = origin.rstrip("/")

    def absolutize(url: str, attr: str) -> str:
        return f"{origin}{url}" if url.startswith("/") else url

    return rewrite_urls(html, absolutize)


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


class _UrlRewriteParser(HTMLParser):
    def __init__(self, callback: Callable[[str, str], str | None]):
        super().__init__(convert_charrefs=False)
        self.callback = callback
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        self.parts.append(self._rewrite_tag(self.get_starttag_text()))

    def handle_startendtag(self, tag: str, attrs):
        self.parts.append(self._rewrite_tag(self.get_starttag_text()))

    def handle_endtag(self, tag: str):
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str):
        self.parts.append(data)

    def handle_entityref(self, name: str):
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str):
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str):
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str):
        self.parts.append(f"<!{decl}>")

    def handle_pi(self, data: str):
        self.parts.append(f"<?{data}>")

    def unknown_decl(self, data: str):
        self.parts.append(f"<![{data}]>")

    def _rewrite_tag(self, raw: str) -> str:
        def replace(match: re.Match) -> str:
            prefix, quote, value = match.group(1), match.group(2), match.group(3)
            name = prefix.split("=", 1)[0].strip().lower()
            if name == "srcset":
                value = self._rewrite_srcset(value)
                if value is None:
                    return ""
            else:
                value = self.callback(value, name)
                if value is None:
                    return ""
            return f"{prefix}{quote}{value}{quote}"

        return ATTRIBUTE_RE.sub(replace, raw)

    def _rewrite_srcset(self, value: str) -> str | None:
        parts = []
        for candidate in value.split(","):
            match = re.match(r"^(\s*)(\S+)(.*)$", candidate, re.DOTALL)
            if match:
                url = self.callback(match.group(2), "srcset")
                if url is None:
                    continue
                candidate = f"{match.group(1)}{url}{match.group(3)}"
            parts.append(candidate)
        value = ",".join(parts).strip()
        return value or None


def strip_toc(html: str) -> str:
    '''
    remove a hand-written "Table of Contents" heading and its balanced list
    '''
    parser = _TocStripper()
    parser.feed(html or "")
    parser.close()
    return "".join(parser.parts)


class _TocStripper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.state = "normal"
        self.h2_parts: list[str] = []
        self.h2_depth = 0
        self.pending: list[str] = []
        self.list_depth = 0

    def handle_starttag(self, tag: str, attrs):
        name = tag.lower()
        raw = self.get_starttag_text()
        if self.state == "collecting_h2":
            if name == "h2":
                self.h2_depth += 1
            self.h2_parts.append(raw)
            return
        if self.state == "pending_heading":
            if name in {"ol", "ul"}:
                self.pending = []
                self.list_depth = 1
                self.state = "skipping_list"
                return
            self._flush_pending()
        if self.state == "skipping_list":
            if name in {"ol", "ul"}:
                self.list_depth += 1
            return
        if name == "h2":
            self.state = "collecting_h2"
            self.h2_depth = 1
            self.h2_parts = [raw]
            return
        self.parts.append(raw)

    def handle_startendtag(self, tag: str, attrs):
        raw = self.get_starttag_text()
        if self.state == "collecting_h2":
            self.h2_parts.append(raw)
            return
        if self.state == "pending_heading":
            self._flush_pending()
        if self.state == "skipping_list":
            return
        self.parts.append(raw)

    def handle_endtag(self, tag: str):
        name = tag.lower()
        if self.state == "collecting_h2":
            if name == "h2":
                self.h2_depth -= 1
                if self.h2_depth == 0:
                    text = text_content("".join(self.h2_parts) + "</h2>").lower()
                    if text == "table of contents":
                        self.pending = self.h2_parts + ["</h2>"]
                        self.state = "pending_heading"
                    else:
                        self.parts.extend(self.h2_parts)
                        self.parts.append("</h2>")
                        self.state = "normal"
                else:
                    self.h2_parts.append("</h2>")
            else:
                self.h2_parts.append(f"</{tag}>")
            return
        if self.state == "pending_heading":
            self._flush_pending()
        if self.state == "skipping_list":
            if name in {"ol", "ul"}:
                self.list_depth -= 1
                if self.list_depth == 0:
                    self.state = "normal"
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str):
        if self.state == "collecting_h2":
            self.h2_parts.append(data)
            return
        if self.state == "pending_heading":
            if data.strip():
                self._flush_pending()
                self.parts.append(data)
            else:
                self.pending.append(data)
            return
        if self.state == "skipping_list":
            return
        self.parts.append(data)

    def handle_entityref(self, name: str):
        self._handle_token(f"&{name};")

    def handle_charref(self, name: str):
        self._handle_token(f"&#{name};")

    def handle_comment(self, data: str):
        self._handle_token(f"<!--{data}-->")

    def handle_decl(self, decl: str):
        self._handle_token(f"<!{decl}>")

    def handle_pi(self, data: str):
        self._handle_token(f"<?{data}>")

    def unknown_decl(self, data: str):
        self._handle_token(f"<![{data}]>")

    def _handle_token(self, raw: str):
        if self.state == "collecting_h2":
            self.h2_parts.append(raw)
            return
        if self.state == "pending_heading":
            self._flush_pending()
        if self.state == "skipping_list":
            return
        self.parts.append(raw)

    def _flush_pending(self):
        if self.state == "pending_heading":
            self.parts.extend(self.pending)
            self.pending = []
            self.state = "normal"

    def close(self):
        super().close()
        if self.state == "collecting_h2":
            self.parts.extend(self.h2_parts)
        else:
            self._flush_pending()


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
