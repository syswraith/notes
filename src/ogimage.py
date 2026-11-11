import os
import re
import sys
import tempfile
from html import unescape
from pathlib import Path

import requests

try:
    from pictex import Canvas, Column, Text, Image
    _PICTEX_AVAILABLE = True
except ModuleNotFoundError as e:
    if "pictex" in str(e):
        print(f"  ! pictex not installed: {e}", file=sys.stderr)
    else:
        raise
    Canvas = Column = Text = Image = None
    _PICTEX_AVAILABLE = False
except Exception as e:
    print(f"  ! pictex import failed: {e}", file=sys.stderr)
    Canvas = Column = Text = Image = None
    _PICTEX_AVAILABLE = False


def _plain(html: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", html or ""))
    return re.sub(r"\s+", " ", text).strip()


def _download_favicon(site_url: str) -> str | None:
    '''
    Download the site favicon from SITE_URL to a temp file.
    Returns the local path, or None if unavailable.
    '''
    base = site_url.rstrip("/")
    for ext in ("ico", "png", "svg"):
        url = f"{base}/favicon.{ext}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and response.content:
                fd, path = tempfile.mkstemp(suffix=f".{ext}")
                with os.fdopen(fd, "wb") as f:
                    f.write(response.content)
                return path
        except requests.RequestException:
            continue
    return None


def generate_thumbnail(post, site_url: str, out_dir: Path) -> str | None:
    '''
    Generate a per-post OpenGraph thumbnail SVG with pictex.
    Returns the relative path (e.g. "1/images/thumbnail.svg") or None.
    '''
    if not _PICTEX_AVAILABLE:
        print("  ! pictex not installed; skipping thumbnail", file=sys.stderr)
        return None

    target = out_dir / str(post.number) / "images" / "thumbnail.svg"
    target.parent.mkdir(parents=True, exist_ok=True)

    favicon_path = _download_favicon(site_url)

    canvas = Canvas().width(1200).height(630).background_color("white")

    children = [
        Text(post.title).font_size(44).font_weight(700).color("#111827"),
        Text(f"by {post.author}").font_size(24).color("#555555"),
    ]
    if post.description:
        children.append(
            Text(_plain(post.description)).font_size(18).font_style("italic").color("#555555")
        )
    if favicon_path:
        children.append(
            Image(favicon_path).size(40, 40).absolute_position(right=30, bottom=30)
        )

    layout = Column(*children).gap(24).padding(50).height(630)

    vector_image = canvas.render_as_svg(layout, embed_font=True)
    vector_image.save(str(target))

    if favicon_path:
        try:
            os.unlink(favicon_path)
        except OSError:
            pass

    return f"{post.number}/images/thumbnail.svg"
