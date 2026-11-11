import os
import sys
from pathlib import Path

from github import Github
from render import (
        Comment,
        Post,
        Site,
        count_comments,
        split_description,
        strip_toc,
        thread_comments,
        )

repo_full = os.getenv("GITHUB_REPOSITORY")
if not repo_full:
    sys.exit("GITHUB_REPOSITORY is not set. Set it to owner/repo; GitHub Actions provides it automatically.")
USER, REPO = repo_full.split("/", 1)
OUT_DIR = Path(__file__).parent.parent / "dist"


def build_post(client: Github, issue: dict) -> Post:
    raw = client.comments(issue["number"]) if issue.get("comments") else []
    comments = thread_comments([
            Comment(
                author=c["user"]["login"],
                author_url=c["user"]["html_url"],
                avatar_url=c["user"]["avatar_url"],
                created_at=c["created_at"],
                body_html=c.get("body_html") or "",
                )
            for c in raw
            ])
    description, body_html = split_description(issue.get("body_html") or "")
    return Post(
            number=issue["number"],
            title=issue["title"],
            author=issue["user"]["login"],
            created_at=issue["created_at"],
            updated_at=issue["updated_at"],
            url=issue["html_url"],
            tags=client.tags(issue),
            description=description,
            body_html=strip_toc(body_html),
            comments=comments,
            )


def main():
    site_url = os.getenv("SITE_URL", "http://localhost:8000")
    site_title = os.getenv("SITE_TITLE", f"{USER}'s microblog")

    client = Github(USER, REPO)
    print(f"Fetching open issues from {USER}/{REPO}...")
    issues = client.blog(n=100)

    posts = []
    for issue in issues:
        print(f"  #{issue['number']} {issue['title']}")
        posts.append(build_post(client, issue))

    site = Site(site_title, USER, REPO, site_url, os.getenv("SITE_DESCRIPTION", ""))
    site.write(posts, OUT_DIR)

    n_comments = sum(count_comments(p.comments) for p in posts)
    print(f"\nBuilt {len(posts)} post(s), {n_comments} comment(s) -> {OUT_DIR}/")
    print(f"Serve with: python -m http.server 8000 -d {OUT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Build failed: {e}", file=sys.stderr)
        sys.exit(1)
