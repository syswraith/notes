# Riff

A minimal static site generator that publishes [microblogs](https://en.wikipedia.org/wiki/Microblogging) from GitHub Issues. Open an issue with the `publish` label to publish; remove the label or close the issue to unpublish. Other labels become tags; comments become threaded replies.

## Using this template

1. On this repository's page, click **Use this template** → **Create a new repository**.
2. Clone your new repository locally.
3. Go to **Settings → Pages → Build and deployment → Source** and select **GitHub Actions**.
4. Push any change (or use the Actions tab → "Run workflow") to trigger the first build.
5. By default, your site deploys to `https://<owner>.github.io/<repo>/`. See [Custom domain](#custom-domain) to serve it from a subdomain instead.

## Writing posts

> [!IMPORTANT]
> Restrict issue creation to collaborators only; otherwise anyone can trigger a workflow by creating an issue!

Open an issue in the repository and add the `publish` label (create it under **Issues → Labels** if it does not exist). The issue title becomes the post title; the body becomes the post content. Use other labels to tag posts; `publish` controls publication and is not shown as a tag. Remove the label or close the issue to unpublish. Issues without the label are ignored.

Math works with `$...$` (inline) and `$$...$$` (block) delimiters via KaTeX.

## How it works

- **Posts** = open GitHub issues carrying the `publish` label. Remove the label or close the issue to unpublish it.
- **Tags** = issue labels other than `publish`.
- **Comments** = issue comments. Quote-replies (comments opening with a blockquote of an earlier comment) are detected and nested under their parent recursively.
- **Bodies** are rendered by GitHub's API (`application/vnd.github.full+json`), so no Markdown library is needed at build time.
- **Images** uploaded to issues are downloaded at build time and served locally; images that cannot be localized are dropped.
- **Math** (`$...$`, `$$...$$`, `\[...\]`, `\( \)`) renders client-side via KaTeX.
- **Feed**: Atom feed at `feed.xml`.
- **OpenGraph**: per-post `thumbnail.png` generated at build time with [pictex](https://pictex.readthedocs.io/), stored under `dist/{issue-number}/images/thumbnail.png` and exposed as `og:image` with `twitter:card: summary_large_image`.
- **404 page**: custom `dist/404.html` served automatically by GitHub Pages for missing routes.

## Project structure

```
src/
  main.py        # Build orchestrator
  github.py      # GitHub API client
  render.py      # Dataclasses, comment threading, site renderer
  htmlutil.py    # HTML rewriting and text helpers
  ogimage.py     # OpenGraph thumbnail generation (pictex)
  templates/     # Jinja2 templates (base, index, post, tags, feed, 404)
  static/        # site.css, syntax.css (water.css loaded from CDN)
dist/            # Generated output (gitignored)
```

## Local setup

```bash
# Install dependencies
uv sync --frozen

# Build (GITHUB_REPOSITORY is automatic in GitHub Actions; set it locally)
GITHUB_REPOSITORY=owner/repo SITE_URL=http://localhost:8000 uv run python src/main.py

# Serve locally
python -m http.server 8000 -d dist
```

## Deployment

The site builds and deploys via GitHub Actions on:

- Issue events (opened, edited, closed, reopened, labeled, unlabeled, transferred)
- Issue comments (created, edited, deleted)
- Pushes to `src/`, `pyproject.toml`, `uv.lock`, or the workflow file

### Custom domain

To serve the site from a subdomain such as `notes.example.com`:

1. In **Settings → Pages → Custom domain**, enter the subdomain and save.
2. At your DNS provider, create a `CNAME` record for the subdomain pointing to `<owner>.github.io` (not the repository URL).
3. Wait for DNS and TLS provisioning, then rerun **Actions → build site → Run workflow**.

Changing Pages settings does not trigger the workflow automatically. The next build uses the custom domain root (`https://notes.example.com/`) instead of `https://<owner>.github.io/<repo>/`. With Actions-based Pages, GitHub stores the custom domain in repository settings, so a `CNAME` file in `dist` is not required.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_REPOSITORY` | Yes (locally) | `owner/repo`. Provided automatically in GitHub Actions. |
| `SITE_URL` | No | Site URL for the Atom feed and absolute links. Defaults to `http://localhost:8000`. In Actions, `configure-pages` supplies it; custom domains use the domain root. |
| `SITE_TITLE` | No | Site title. Defaults to `"{USER}'s {REPO}"`. |
| `SITE_DESCRIPTION` | No | Site description used in metadata and link previews. |
| `PUBLISH_LABEL` | No | Label required to publish an issue. Defaults to `publish`; create the label in the repository if needed. |
| `GITHUB_TOKEN` | No | Authenticated GitHub API access (5000/hr vs 60/hr unauthenticated). Provided automatically in Actions. |

> **Note:** `SITE_URL` must be a publicly reachable URL (not `localhost`) for Discord, Twitter, and other link-preview crawlers to fetch `og:image`. Locally you can use `http://localhost:8000` for testing, but thumbnails won't appear in embeds until the site is deployed to a public URL.

