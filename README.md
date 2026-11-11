# Riff

A minimal static site generator that publishes [microblogs](https://en.wikipedia.org/wiki/Microblogging) from GitHub Issues. Open an issue to publish; close it to unpublish. Labels become tags; comments become threaded replies.

## Using this template

1. On this repository's page, click **Use this template** → **Create a new repository**.
2. Clone your new repository locally.
3. Go to **Settings → Pages → Build and deployment → Source** and select **GitHub Actions**.
4. Push any change (or use the Actions tab → "Run workflow") to trigger the first build.
5. Your site deploys to `https://<owner>.github.io/<repo>/`.

## How it works

- **Posts** = open GitHub issues. Close an issue to unpublish it.
- **Tags** = issue labels.
- **Comments** = issue comments. Quote-replies (comments opening with a blockquote of an earlier comment) are detected and nested under their parent recursively.
- **Bodies** are rendered by GitHub's API (`application/vnd.github.full+json`), so no Markdown library is needed at build time.
- **Images** uploaded to issues are downloaded at build time and served locally — no short-lived signed URLs.
- **Math** (`$...$`, `$$...$$`, `\[...\]`, `\( \)`) renders client-side via KaTeX.
- **Feed**: Atom feed at `feed.xml`.
- **OpenGraph**: per-post `thumbnail.png` generated at build time with [pictex](https://pictex.readthedocs.io/), stored under `dist/{issue-number}/images/thumbnail.png` and exposed as `og:image` with `twitter:card: summary_large_image`.
- **404 page**: custom `dist/404.html` served automatically by GitHub Pages for missing routes.

## Local setup

```bash
# Install dependencies
uv sync --frozen

# Build (GITHUB_REPOSITORY is automatic in GitHub Actions; set it locally)
GITHUB_REPOSITORY=owner/repo SITE_URL=http://localhost:8000 uv run python src/main.py

# Serve locally
python -m http.server 8000 -d dist
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_REPOSITORY` | Yes (locally) | `owner/repo`. Provided automatically in GitHub Actions. |
| `SITE_URL` | No | Site URL for the Atom feed and absolute links. Defaults to `http://localhost:8000`. |
| `SITE_TITLE` | No | Site title. Defaults to `"{USER}'s {REPO}"`. |
| `SITE_DESCRIPTION` | No | Site description used on the homepage. |
| `GITHUB_TOKEN` | No | Authenticated GitHub API access (5000/hr vs 60/hr unauthenticated). Provided automatically in Actions. |

> **Note:** `SITE_URL` must be a publicly reachable URL (not `localhost`) for Discord, Twitter, and other link-preview crawlers to fetch `og:image`. Locally you can use `http://localhost:8000` for testing, but thumbnails won't appear in embeds until the site is deployed to a public URL.

## Deployment

The site builds and deploys via GitHub Actions on:

- Issue events (opened, edited, closed, reopened, labeled, unlabeled, transferred)
- Issue comments (created, edited, deleted)
- Pushes to `src/`, `pyproject.toml`, `uv.lock`, or the workflow file

Add the workflow (included in the template) to `.github/workflows/build.yml`. After enabling Pages with **GitHub Actions** as the source, the site deploys automatically on every push, issue event, or comment.

## Writing posts

> [!IMPORTANT]
<<<<<<< HEAD
> Change the "Issue Creation" from anyone to "Collaborators only" else anyone can create Issues!

Open an issue in the repository. The issue title becomes the post title; the body becomes the post content. Use labels to tag posts. Close the issue to unpublish. 
=======
> Restrict issue creation to collaborators only else anyone can trigger a workflow by creating an issue!

Open an issue in the repository. The issue title becomes the post title; the body becomes the post content. Use labels to tag posts. Close the issue to unpublish.
>>>>>>> upstream/master

Math works with `$...$` (inline) and `$$...$$` (block) delimiters via KaTeX.

## Project structure

```
src/
  main.py        # Build orchestrator
  github.py      # GitHub API client
  render.py      # Dataclasses, comment threading, site renderer
  ogimage.py     # OpenGraph thumbnail generation (pictex)
  templates/     # Jinja2 templates (base, index, post, tags, feed, 404)
  static/        # awsm.css, site.css, syntax.css
dist/            # Generated output (gitignored)
```

## License

MIT
