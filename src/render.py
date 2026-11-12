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

from htmlutil import absolutize_html, leading_blockquote, rewrite_urls, text_content
from ogimage import download_favicon, generate_thumbnail

SRC_DIR = Path(__file__).parent
TEMPLATES_DIR = SRC_DIR / "templates"
STATIC_DIR = SRC_DIR / "static"

TOC_RE = re.compile(
        r'<h2[^>]*>\s*Table of Contents\s*</h2>\s*<ol[^>]*>.*?</ol>',
        re.DOTALL | re.IGNORECASE,
        )
IMAGE_URL_RE = re.compile(
        r'https?://(?:private-user-images|user-images)\.githubusercontent\.com/'
        r'|https?://github\.com/user-attachments/assets/',
        re.IGNORECASE,
        )


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


def latest_updated(posts: list["Post"]) -> str:
    timestamps = []
    for post in posts:
        value = post.updated_at or post.created_at
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        timestamps.append(parsed)
    latest = max(timestamps, default=datetime.now(timezone.utc))
    return latest.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def anchor(name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    return slug or "tag"


def tag_anchor_map(posts: list["Post"]) -> dict[str, str]:
    anchors: dict[str, str] = {}
    used: set[str] = set()
    for post in posts:
        for tag in post.tags:
            if tag in anchors:
                continue
            base = anchor(tag)
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base}-{suffix}"
                suffix += 1
            anchors[tag] = candidate
            used.add(candidate)
    return anchors


def plural(n: int) -> str:
    return "" if n == 1 else "s"


def _plain(html: str) -> str:
    return text_content(html)


def cdata(text: str) -> str:
    return text.replace("]]>", "]]]]><![CDATA[>")


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
    seen: list[tuple[Comment, str]] = []
    for comment in comments:
        original = comment.body_html
        quote, remainder = leading_blockquote(original)
        parent = None
        if quote is not None:
            for prev, prev_original in reversed(seen):
                if _is_quote_reply(quote, prev.body_html) or _is_quote_reply(quote, prev_original):
                    parent = prev
                    break
        if parent is None:
            roots.append(comment)
        else:
            comment.body_html = remainder.lstrip()
            parent.replies.append(comment)
        seen.append((comment, original))
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
    quote, remainder = leading_blockquote(body_html)
    if quote is None:
        return "", body_html
    return quote, remainder.lstrip()


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
        parsed = urlparse(self.site_url)
        self.tld = f"{parsed.scheme}://{parsed.netloc}/"

        self.env = Environment(
                loader=FileSystemLoader(TEMPLATES_DIR),
                autoescape=select_autoescape(("html", "xml")),
                trim_blocks=True,
                lstrip_blocks=True,
                )
        self.env.filters.update(
                datefmt=datefmt,
                anchor=anchor,
                plural=plural,
                count_comments=count_comments,
                absolutize=self.absolutize,
                cdata=cdata,
                )
        self.env.globals.update(
                site_title=title,
                user=user,
                repo=repo,
                base=self.base,
                tld=self.tld,
                absurl=self.absurl,
                )

    def absurl(self, rel: str = "") -> str:
        site = self.site_url.rstrip("/")
        if rel:
            return f"{site}/{rel.lstrip('/')}"
        return f"{site}/"

    def absolutize(self, html: str) -> str:
        return absolutize_html(html, self.tld)

    def _render(self, template: str, out: Path, **context):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.env.get_template(template).render(**context))

    def _localize_images(self, html: str, img_dir: Path, prefix: str) -> str:
        '''
        GitHub serves user-uploaded images from short-lived signed URLs;
        download them and point every src, href or srcset at the local copy.
        Images that cannot be copied locally are dropped rather than left
        pointing at an expiring URL.
        '''
        def localize(url: str, attr: str) -> str | None:
            remote = unescape(url)
            signed = attr in {"poster", "src", "srcset"} and "jwt=" in remote.lower()
            if not (IMAGE_URL_RE.match(remote) or signed):
                return url
            path = urlparse(remote).path
            key = f"{urlparse(remote).netloc}{path}"
            name = f"{hashlib.sha1(key.encode()).hexdigest()[:16]}{Path(path).suffix or '.png'}"
            target = img_dir / name
            if not target.exists():
                try:
                    response = requests.get(remote, timeout=30)
                    response.raise_for_status()
                    img_dir.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(response.content)
                except (requests.RequestException, OSError) as e:
                    print(f"  ! dropping image {name}: {e}", file=sys.stderr)
                    return None
            return f"{prefix}{name}"

        return rewrite_urls(html, localize)

    def _localize_comments(self, comments: list[Comment], img_dir: Path, prefix: str):
        for comment in comments:
            comment.body_html = self._localize_images(comment.body_html, img_dir, prefix)
            self._localize_comments(comment.replies, img_dir, prefix)

    def write(self, posts: list[Post], out_dir: Path, site_url: str | None = None):
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True)
        shutil.copytree(STATIC_DIR, out_dir / "static")

        site_url = site_url or self.site_url
        favicon = download_favicon(site_url)
        thumbs: dict[int, str] = {}
        try:
            for post in posts:
                try:
                    thumb = generate_thumbnail(post, out_dir, favicon)
                except Exception as e:
                    print(f"  ! skipping thumbnail for #{post.number}: {e}", file=sys.stderr)
                    thumb = None
                if thumb:
                    thumbs[post.number] = thumb
        finally:
            if favicon:
                try:
                    Path(favicon).unlink()
                except OSError:
                    pass

        site_thumb = next(iter(thumbs.values()), None)
        tag_anchors = tag_anchor_map(posts)

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
            self._render("post.html", page, post=post, newer=newer, older=older, og=og, tag_anchors=tag_anchors)

        tags: dict[str, list[Post]] = {}
        for post in posts:
            for tag in post.tags:
                tags.setdefault(tag, []).append(post)
        tags_og = {
                "title": f"Tags · {self.title}",
                "type": "website",
                "description": self.description,
                "tags": [],
                }
        if site_thumb:
            tags_og["image"] = self.absurl(site_thumb)
        self._render(
                "tags.html",
                out_dir / "tags.html",
                tags=tags,
                og={**tags_og, "url": self.absurl("tags.html")},
                tag_anchors=tag_anchors,
                )
        self._render(
                "tags.html",
                out_dir / "tags" / "index.html",
                tags=tags,
                og={**tags_og, "url": self.absurl("tags/")},
                tag_anchors=tag_anchors,
                )

        self._render("404.html", out_dir / "404.html", og={"title": f"404 · {self.title}", "url": self.absurl("404.html"), "type": "website"})

        feed_updated = latest_updated(posts)
        self._render("feed.xml", out_dir / "feed.xml", posts=posts, feed_updated=feed_updated)
