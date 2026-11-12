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

    def _get_all(self, url: str, accept: str, params: dict | None = None) -> list[dict]:
        '''
        follow GitHub's pagination links and return every item
        '''
        params = dict(params or {}, per_page=100)
        items: list[dict] = []
        while url:
            response = requests.get(url, headers=self._get_headers(accept), params=params, timeout=30)
            response.raise_for_status()
            items.extend(response.json())
            url = response.links.get("next", {}).get("url")
            params = None
        return items

    def tags(self, issue, exclude: str | None = None) -> list[str]:
        '''
        get the labels associated with the issue
        '''
        return [
                label["name"]
                for label in issue.get("labels", [])
                if not exclude or label["name"].casefold() != exclude.casefold()
                ]

    def comments(self, issue_id: int):
        '''
        get the discussion associated with the issue,
        bodies pre-rendered as HTML in body_html
        '''
        url = f"{self.base_url}/issues/{issue_id}/comments"
        return self._get_all(url, "application/vnd.github.full+json")

    def blog(self, label: str | None = None):
        '''
        get all open, non-pull-request issues, newest first,
        optionally restricted to issues carrying the given label;
        bodies available as raw markdown (body) and HTML (body_html)
        '''
        url = f"{self.base_url}/issues"
        params = {
                "sort": "created",
                "direction": "desc",
                "state": "open"
                }
        if label:
            params["labels"] = label
        return [
                issue
                for issue in self._get_all(url, "application/vnd.github.full+json", params)
                if "pull_request" not in issue
                and (
                    not label
                    or any(name.casefold() == label.casefold() for name in self.tags(issue))
                    )
                ]
