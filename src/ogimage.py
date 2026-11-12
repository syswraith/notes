import os
import re
import sys
import tempfile
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

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


def download_favicon(site_url: str) -> str | None:
    '''
    Download the site favicon from the domain root of SITE_URL to a temp file.
    Returns the local path, or None if unavailable.
    '''
    parsed = urlparse(site_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    image_types = {"image/x-icon", "image/vnd.microsoft.icon", "image/ico", "image/png"}
    for ext in ("ico", "png"):
        url = f"{base}/favicon.{ext}"
        try:
            response = requests.get(url, timeout=10)
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if response.status_code == 200 and response.content and content_type in image_types:
                fd, path = tempfile.mkstemp(suffix=f".{ext}")
                with os.fdopen(fd, "wb") as f:
                    f.write(response.content)
                return path
        except requests.RequestException:
            continue
    return None


def generate_thumbnail(post, out_dir: Path, favicon_path: str | None = None) -> str | None:
    '''
    Generate a per-post OpenGraph thumbnail PNG with pictex.
    Returns the relative path (e.g. "1/images/thumbnail.png") or None.
    '''
    if not _PICTEX_AVAILABLE:
        print("  ! pictex not installed; skipping thumbnail", file=sys.stderr)
        return None

    target = out_dir / str(post.number) / "images" / "thumbnail.png"
    target.parent.mkdir(parents=True, exist_ok=True)

    canvas = Canvas().width(1200).height(630).background_color("white").font_family("DejaVu Sans")

    children = [
        Text(post.title).font_size(72).font_weight(800).color("#111827"),
        Text(f"by {post.author}").font_size(32).color("#555555"),
    ]
    if post.description:
        children.append(
            Text(_plain(post.description)).font_size(28).font_style("italic").color("#555555")
        )
    if favicon_path:
        children.append(
            Image(favicon_path).size(64, 64).absolute_position(right=30, bottom=30)
        )

    layout = Column(*children).gap(32).padding(60).height(630)

    image = canvas.render(layout)
    image.save(str(target))

    if favicon_path:
        try:
            os.unlink(favicon_path)
        except OSError:
            pass

    return f"{post.number}/images/thumbnail.png"
