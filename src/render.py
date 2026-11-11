import hashlib
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ogimage import generate_thumbnail

SRC_DIR = Path(__file__).parent
TEMPLATES_DIR = SRC_DIR / "templates"
STATIC_DIR = SRC_DIR / "static"

QUOTE_RE = re.compile(r"^\s*<blockquote>(.*?)</blockquote>", re.DOTALL)
TOC_RE = re.compile(
        r'<h2[^>]*>\s*Table of Contents\s*</h2>\s*<ol[^>]*>.*?</ol>',
        re.DOTALL | re.IGNORECASE,
        )
URL_RE = re.compile(r'https://private-user-images\.githubusercontent\.com/[^"\s]+')


@dataclass
class Comment:
    author: str
    author_url: str
    created_at: str
    body_html: str
    replies: list["Comment"] = field(default_factory=list)


@dataclass
class Post:
    number: int
    title: str
    author: str
    created_at: str
    updated_at: str
    url: str
    tags: list[str]
    description: str
    body_html: str
    comments: list[Comment]


def datefmt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return (iso or "")[:10]


def anchor(name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    return slug or "tag"


def plural(n: int) -> str:
    return "" if n == 1 else "s"


def _plain(html: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\s+", " ", text).replace("…", "").strip()


def _is_quote_reply(quote: str, earlier: str) -> bool:
    a, b = _plain(quote), _plain(earlier)
    if len(a) < 20 or not b:
        return False
    return b.startswith(a[:40]) or a.startswith(b[:40])


def thread_comments(comments: list[Comment]) -> list[Comment]:
    '''
    GitHub issue comments are flat; a "reply" there is a new comment
    that opens with a blockquote of the comment it replies to.
    Detect those, strip the quote and nest them under their parent.
    '''
    roots: list[Comment] = []
    seen: list[Comment] = []
    for comment in comments:
        parent = None
        quote = QUOTE_RE.match(comment.body_html)
        if quote:
            for prev in reversed(seen):
                if _is_quote_reply(quote.group(1), prev.body_html):
                    parent = prev
                    break
        if parent is None:
            roots.append(comment)
        else:
            comment.body_html = comment.body_html[quote.end():].lstrip()
            parent.replies.append(comment)
        seen.append(comment)
    return roots


def count_comments(comments: list[Comment]) -> int:
    total = 0
    stack = list(comments)
    while stack:
        current = stack.pop()
        total += 1
        stack.extend(current.replies)
    return total


def split_description(body_html: str) -> tuple[str, str]:
    '''
    pull the leading blockquote out of a post body: (description, rest)
    '''
    quote = QUOTE_RE.match(body_html)
    if not quote:
        return "", body_html
    return quote.group(1), body_html[quote.end():].lstrip()


def strip_toc(body_html: str) -> str:
    '''
    remove the hand-written "Table of Contents" heading and list
    '''
    return TOC_RE.sub("", body_html)


def _clip(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" .,;:") + "…"


def _post_description(post: Post) -> str:
    text = _plain(post.description) if post.description else _plain(post.body_html)
    return _clip(text)


class Site:
    '''
    renders posts into a static site
    '''

    def __init__(self, title: str, user: str, repo: str, site_url: str, description: str = ""):
        self.title = title
        self.description = description
        self.user = user
        self.repo = repo
        self.site_url = site_url.rstrip("/")
        path = urlparse(self.site_url).path.strip("/")
        self.base = f"/{path}/" if path else "/"

        self.env = Environment(
                loader=FileSystemLoader(TEMPLATES_DIR),
                autoescape=select_autoescape(("html", "xml")),
                trim_blocks=True,
                lstrip_blocks=True,
                )
        self.env.filters.update(datefmt=datefmt, anchor=anchor, plural=plural, count_comments=count_comments)
        self.env.globals.update(
                site_title=title,
                user=user,
                repo=repo,
                base=self.base,
                absurl=self.absurl,
                )

    def absurl(self, rel: str = "") -> str:
        site = self.site_url.rstrip("/")
        if rel:
            return f"{site}/{rel.lstrip('/')}"
        return f"{site}/"

    def _render(self, template: str, out: Path, **context):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.env.get_template(template).render(**context))

    def _localize_images(self, html: str, img_dir: Path, prefix: str) -> str:
        '''
        GitHub serves user-uploaded images from short-lived signed URLs;
        download them and point every src, href or srcset at the local copy
        '''
        def localize(match: re.Match) -> str:
            url = match.group(0)
            path = urlparse(url).path
            name = f"{hashlib.sha1(path.encode()).hexdigest()[:16]}{Path(path).suffix or '.png'}"
            target = img_dir / name
            if not target.exists():
                try:
                    response = requests.get(unescape(url), timeout=30)
                    response.raise_for_status()
                    img_dir.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(response.content)
                except (requests.RequestException, OSError) as e:
                    print(f"  ! keeping remote image {name}: {e}", file=sys.stderr)
                    return match.group(0)
            return f"{prefix}{name}"

        return URL_RE.sub(localize, html)

    def _localize_comments(self, comments: list[Comment], img_dir: Path, prefix: str):
        for comment in comments:
            comment.body_html = self._localize_images(comment.body_html, img_dir, prefix)
            self._localize_comments(comment.replies, img_dir, prefix)

    def write(self, posts: list[Post], out_dir: Path, site_url: str | None = None):
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True)
        shutil.copytree(STATIC_DIR, out_dir / "static")

        site_url = site_url or self.site_url
        thumbs: dict[int, str] = {}
        for post in posts:
            thumb = generate_thumbnail(post, site_url, out_dir)
            if thumb:
                thumbs[post.number] = thumb

        site_thumb = next(iter(thumbs.values()), None)

        for post in posts:
            img_dir = out_dir / str(post.number) / "images"
            prefix = f"{self.base}{post.number}/images/"
            post.description = self._localize_images(post.description, img_dir, prefix)
            post.body_html = self._localize_images(post.body_html, img_dir, prefix)
            self._localize_comments(post.comments, img_dir, prefix)

        site_og = {
                "title": self.title,
                "url": self.absurl(),
                "type": "website",
                "description": self.description,
                "tags": [],
                }
        if site_thumb:
            site_og["image"] = self.absurl(site_thumb)
        self._render("index.html", out_dir / "index.html", posts=posts, og=site_og)

        for i, post in enumerate(posts):
            page = out_dir / str(post.number) / "index.html"
            newer = posts[i - 1] if i > 0 else None
            older = posts[i + 1] if i + 1 < len(posts) else None
            og = {
                    "title": post.title,
                    "url": self.absurl(f"{post.number}/"),
                    "type": "article",
                    "description": _post_description(post),
                    "published": post.created_at,
                    "tags": post.tags,
                    }
            thumb = thumbs.get(post.number)
            if thumb:
                og["image"] = self.absurl(thumb)
            self._render("post.html", page, post=post, newer=newer, older=older, og=og)

        tags: dict[str, list[Post]] = {}
        for post in posts:
            for tag in post.tags:
                tags.setdefault(tag, []).append(post)
        tags_og = {
                "title": f"Tags · {self.title}",
                "url": self.absurl("tags.html"),
                "type": "website",
                "description": self.description,
                "tags": [],
                }
        if site_thumb:
            tags_og["image"] = self.absurl(site_thumb)
        self._render("tags.html", out_dir / "tags.html", tags=tags, og=tags_og)
        self._render("tags.html", out_dir / "tags" / "index.html", tags=tags, og=tags_og)

        self._render("404.html", out_dir / "404.html", og={"title": f"404 · {self.title}", "url": self.absurl("404.html"), "type": "website"})

        feed_updated = max(
                (p.updated_at or p.created_at for p in posts),
                default=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
        self._render("feed.xml", out_dir / "feed.xml", posts=posts, feed_updated=feed_updated)
