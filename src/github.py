import os

import requests

class Github:
    def _get_headers(self, accept: str = "application/vnd.github+json"):
        headers = {
                "Accept": accept,
                "X-GitHub-Api-Version": "2022-11-28"
                }
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def __init__(self, user: str, repo: str):
        self.user = user
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{user}/{repo}"

    def tags(self, issue) -> list[str]:
        '''
        get the labels associated with the issue
        '''
        return [label["name"] for label in issue.get("labels", [])]

    def comments(self, issue_id: int):
        '''
        get the discussion associated with the issue,
        bodies pre-rendered as HTML in body_html
        '''
        url = f"{self.base_url}/issues/{issue_id}/comments"
        headers = self._get_headers("application/vnd.github.full+json")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def blog(self, n: int = 10):
        '''
        get open, non-pull-request issues, newest first,
        bodies available as raw markdown (body) and HTML (body_html)
        '''
        url = f"{self.base_url}/issues"
        params = {
                "per_page": n,
                "sort": "created",
                "direction": "desc",
                "state": "open"
                }
        headers = self._get_headers("application/vnd.github.full+json")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return [i for i in response.json() if "pull_request" not in i]

    def get_post_markdown(self, issue, tags: list[str]) -> str:
        """
        Takes an issue dictionary and returns a single Markdown string
        containing YAML frontmatter and the issue body (no comments).
        """
        if tags is None:
            tags = [label["name"] for label in issue.get("labels", [])]

        title = issue.get("title", "Untitled")
        date = issue.get("created_at", "")[:10]
        updated_at = issue.get("updated_at", "")[:10]
        url = issue.get("html_url", "")
        body = issue.get("body", "")

        # Construct YAML Frontmatter
        frontmatter = "---\n"
        frontmatter += f'title: "{title}"\n'
        frontmatter += f'date: "{date}"\n'
        if updated_at and updated_at != date:
            frontmatter += f'updated_at: "{updated_at}"\n'
        frontmatter += f'url: "{url}"\n'
        frontmatter += f'tags: {tags}\n'
        frontmatter += "---\n\n"

        return frontmatter + body
