# SPDX-License-Identifier: MIT
"""Issue links: a prefilled "raise an issue" URL for GitHub or Azure DevOps (round 3, P1d).

Owner 2026-11-15: issues link to requirements ALL THREE WAYS — the id in the title, a `req:<ID>`
label (an ADO tag), and a marker line `clew-req: <ID>` in the body — so whichever one a tracker
keeps, the link survives. The page only carries a URL: nothing is sent anywhere until a person
opens it and submits the tracker's own form.

The tracker is DECLARED (`wiki.issues: {github: owner/repo}` or `{ado: org/project}`), or read
from the repository's `origin` remote; an unrecognised host gives NO link — a guessed tracker
would file issues somewhere nobody reads.

READ AND WRITE (round 3, P3a): `IssueProvider` lists a tracker's open issues and creates or
labels one, over stdlib REST — GitHub REST v3 and Azure DevOps 7.0 — with the token from the
environment. `link_issues` ties open issues to requirements all three ways. The build fetches
only when `wiki.issues.fetch` is true.

@brief Prefilled issue URLs, tracker discovery, issue providers and linking.
@version 2
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

## (provider, project): ("github", "owner/repo") or ("ado", "org/project").
Target = tuple[str, str]

_GITHUB = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
_ADO_HTTPS = re.compile(r"dev\.azure\.com/([^/\s]+)/([^/\s]+)/_git/")
_ADO_SSH = re.compile(r"ssh\.dev\.azure\.com:v3/([^/\s]+)/([^/\s]+)/")
_ADO_LEGACY = re.compile(r"//([^./\s]+)\.visualstudio\.com/(?:DefaultCollection/)?([^/\s]+)/_git/")


## @brief The tracker a remote URL belongs to.
## @param url A git remote URL (https or ssh).
## @return The target, or None for a host clew does not know.
## @version 1
## @req REQ-DDB-WIKI-022
def target_from_remote(url: str) -> Target | None:
    """@brief Recognise GitHub and Azure DevOps remotes. @return Target or None."""
    url = url.strip()
    found = _GITHUB.search(url)
    if found:
        return "github", f"{found.group(1)}/{found.group(2)}"
    for pattern in (_ADO_HTTPS, _ADO_SSH, _ADO_LEGACY):
        found = pattern.search(url)
        if found:
            return "ado", f"{found.group(1)}/{found.group(2)}"
    return None


## @brief The repository's tracker: declared, else its origin remote's, else none.
## @param declared The `wiki.issues` declaration, or None.
## @param enabled False when issue links are switched off.
## @param repo_root The repository.
## @return The target or None.
## @version 1
## @req REQ-DDB-WIKI-022
def resolve_target(declared: Target | None, enabled: bool, repo_root: Path) -> Target | None:
    """THROUGH THE HARDENED GIT ENVIRONMENT, like every git call: the repository's own config
    is data here, never something that runs.

    @brief Resolve the tracker.
    @return Target or None.
    """
    from ..gitenv import git_argv

    if not enabled or declared:
        return declared if enabled else None
    try:
        out = subprocess.run(
            git_argv("config", "--get", "remote.origin.url"),
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return target_from_remote(out.stdout) if out.stdout.strip() else None


## @brief A prefilled new-issue URL carrying the requirement id three ways.
## @param target The tracker.
## @param req_id The requirement.
## @param title The issue title (the id is prefixed when absent).
## @param body The issue body; the `clew-req:` marker line is appended.
## @return The URL.
## @version 1
## @req REQ-DDB-WIKI-022
def issue_url(target: Target, req_id: str, title: str, body: str) -> str:
    """@brief Build the URL. @return URL."""
    provider, project = target
    title = title if req_id in title else f"{req_id}: {title}"
    body = f"{body}\n\nclew-req: {req_id}".lstrip()
    label = f"req:{req_id}"
    if provider == "github":
        query = urlencode({"title": title, "labels": label, "body": body})
        return f"https://github.com/{project}/issues/new?{query}"
    query = urlencode(
        {"[System.Title]": title, "[System.Tags]": label, "[System.Description]": body}
    )
    return f"https://dev.azure.com/{project}/_workitems/create/Issue?{query}"


# --- read and write side (round 3, P3a) -----------------------------------------------------------


## @brief One open issue or work item.
## @version 1
@dataclass(frozen=True)
class Issue:
    """@brief Id, title, body, labels (ADO tags), web URL, state. @version 1"""

    id: str
    title: str
    body: str
    labels: tuple[str, ...]
    url: str
    state: str


## @brief A tracker over stdlib REST: list open issues, create one, label one.
## @version 1
class IssueProvider(ABC):
    """THE BASE HOLDS THE LOGIC — pagination, the request plumbing, the three-ways linking a
    created issue carries — and a provider only names its endpoints and parses its payloads.
    The opener is injected, so tests answer from canned fixtures and nothing reaches a network.

    @brief Issue tracker base.
    @version 1
    """

    ## @brief Hold the project, token and opener.
    ## @param project `owner/repo` (GitHub) or `org/project` (Azure DevOps).
    ## @param token An API token, or None (public read only).
    ## @param opener A `urlopen`-compatible callable.
    ## v2: a listing cut at its page cap is disclosed (2.0.0, R5-CFG D14)
    ## @version 2
    ## @utility
    def __init__(self, project: str, token: str | None = None, opener: Any = None) -> None:
        """@brief Store. @return None."""
        self.project = project
        self.token = token
        self.opener = opener or urlopen
        ## True when the last listing stopped at its page cap with pages left (D14, 2.0.0).
        self.truncated = False

    ## @brief Every open issue.
    ## @return Issues, in the tracker's order.
    ## @version 1
    ## @req REQ-DDB-WIKI-028
    def list_open(self) -> list[Issue]:
        """@brief List. @return Issues."""
        return self._list()

    ## @brief Create an issue carrying the requirement id in its title, as a `req:` label and as a
    ## marker line.
    ## @param req_id The requirement.
    ## @param title The title (the id is prefixed when absent).
    ## @param body The body; the marker line is appended.
    ## @return (id, web URL).
    ## @version 1
    ## @req REQ-DDB-WIKI-028
    def create(self, req_id: str, title: str, body: str) -> tuple[str, str]:
        """@brief Create. @return Id and URL."""
        title = title if req_id in title else f"{req_id}: {title}"
        body = f"{body}\n\nclew-req: {req_id}".lstrip()
        return self._create(title, body, f"req:{req_id}")

    ## @brief Send one request and decode its JSON reply.
    ## @param method HTTP method.
    ## @param url The URL.
    ## @param payload A JSON-able body, or None.
    ## @param content_type The body's content type.
    ## @return The decoded reply.
    ## @version 1
    ## @utility
    def _call(
        self, method: str, url: str, payload: Any = None, content_type: str = "application/json"
    ) -> Any:
        """@brief Request. @return JSON."""
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(url, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", content_type)
        for key, value in self._auth().items():
            request.add_header(key, value)
        with self.opener(request, timeout=30) as reply:
            return json.loads(reply.read().decode("utf-8") or "null")

    ## @brief Authentication headers.
    ## @return Headers.
    ## @version 1
    ## @utility
    @abstractmethod
    def _auth(self) -> dict[str, str]:
        """@brief Auth. @return Headers."""

    ## @brief The open issues.
    ## @return Issues.
    ## @version 1
    ## @utility
    @abstractmethod
    def _list(self) -> list[Issue]:
        """@brief List. @return Issues."""

    ## @brief Create one issue.
    ## @param title Title.
    ## @param body Body.
    ## @param label The `req:` label.
    ## @return (id, web URL).
    ## @version 1
    ## @utility
    @abstractmethod
    def _create(self, title: str, body: str, label: str) -> tuple[str, str]:
        """@brief Create. @return Id and URL."""


## @brief GitHub issues (REST v3).
## @version 1
class GitHubIssues(IssueProvider):
    """@brief GitHub. @version 1"""

    _API = "https://api.github.com/repos"

    ## @brief Bearer token when one is set.
    ## @return Headers.
    ## @version 1
    ## @utility
    def _auth(self) -> dict[str, str]:
        """@brief Auth. @return Headers."""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    ## @brief Pages of 100 until a short page; pull requests are not issues.
    ## @return Issues.
    ## v2: a listing cut at its page cap is disclosed (2.0.0, R5-CFG D14)
    ## @version 2
    ## @utility
    def _list(self) -> list[Issue]:
        """@brief List. @return Issues."""
        rows, self.truncated = fetch_pages(
            lambda page: self._call(
                "GET", f"{self._API}/{self.project}/issues?state=open&per_page=100&page={page}"
            ),
            _MAX_PAGES,
        )
        return [_gh_issue(r) for r in rows if "pull_request" not in r]

    ## @brief Create through the issues endpoint.
    ## @param title Title.
    ## @param body Body.
    ## @param label The `req:` label.
    ## @return (number, web URL).
    ## @version 1
    ## @utility
    def _create(self, title: str, body: str, label: str) -> tuple[str, str]:
        """@brief Create. @return Id and URL."""
        made = self._call(
            "POST",
            f"{self._API}/{self.project}/issues",
            {"title": title, "body": body, "labels": [label]},
        )
        return str(made["number"]), str(made.get("html_url") or "")


## @brief Azure DevOps work items (REST 7.0).
## @version 1
class AdoIssues(IssueProvider):
    """@brief Azure DevOps. @version 1"""

    ## @brief Basic auth with an empty user and the PAT, when one is set.
    ## @return Headers.
    ## @version 1
    ## @utility
    def _auth(self) -> dict[str, str]:
        """@brief Auth. @return Headers."""
        if not self.token:
            return {}
        return {"Authorization": "Basic " + base64.b64encode(f":{self.token}".encode()).decode()}

    ## @brief A WIQL query for open items, then their fields in batches of 200.
    ## @return Issues.
    ## @version 1
    ## @utility
    def _list(self) -> list[Issue]:
        """@brief List. @return Issues."""
        base = f"https://dev.azure.com/{self.project}/_apis/wit"
        found = self._call("POST", f"{base}/wiql?api-version=7.0", {"query": _WIQL})
        ids = [str(w["id"]) for w in (found or {}).get("workItems", [])]
        out: list[Issue] = []
        for i in range(0, len(ids), 200):
            url = (
                f"{base}/workitems?ids={','.join(ids[i : i + 200])}"
                f"&fields={_ADO_FIELDS}&api-version=7.0"
            )
            out += [self._issue(v) for v in (self._call("GET", url) or {}).get("value", [])]
        return out

    ## @brief One work item as an issue.
    ## @param item The REST row.
    ## @return The issue.
    ## @version 1
    ## @utility
    def _issue(self, item: dict) -> Issue:
        """@brief Convert. @return Issue."""
        fields = item.get("fields") or {}
        tags = tuple(
            t.strip() for t in str(fields.get("System.Tags") or "").split(";") if t.strip()
        )
        return Issue(
            str(item["id"]),
            str(fields.get("System.Title") or ""),
            str(fields.get("System.Description") or ""),
            tags,
            f"https://dev.azure.com/{self.project}/_workitems/edit/{item['id']}",
            str(fields.get("System.State") or ""),
        )

    ## @brief Create an Issue work item with a JSON-patch document.
    ## @param title Title.
    ## @param body Description.
    ## @param label The `req:` tag.
    ## @return (id, web URL).
    ## @version 1
    ## @utility
    def _create(self, title: str, body: str, label: str) -> tuple[str, str]:
        """@brief Create. @return Id and URL."""
        patch = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": body},
            {"op": "add", "path": "/fields/System.Tags", "value": label},
        ]
        url = f"https://dev.azure.com/{self.project}/_apis/wit/workitems/$Issue?api-version=7.0"
        made = self._call("POST", url, patch, "application/json-patch+json")
        wid = str(made["id"])
        return wid, f"https://dev.azure.com/{self.project}/_workitems/edit/{wid}"


## @brief The provider for a tracker, its token read from the environment.
## @param target (provider, project).
## @param opener A `urlopen`-compatible callable, or None.
## @return The provider.
## @version 1
## @req REQ-DDB-WIKI-028
def provider_for(target: Target, opener: Any = None) -> IssueProvider:
    """TOKENS COME FROM THE ENVIRONMENT, never the config file: `GITHUB_TOKEN` / `GH_TOKEN`,
    `AZURE_DEVOPS_EXT_PAT` / `ADO_PAT`.

    @brief Provider.
    @return Provider.
    """
    provider, project = target
    if provider == "github":
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        return GitHubIssues(project, token, opener)
    token = os.environ.get("AZURE_DEVOPS_EXT_PAT") or os.environ.get("ADO_PAT")
    return AdoIssues(project, token, opener)


## @brief Link open issues to requirements: id in title or body, `req:` label, marker line.
## @param issues The open issues.
## @param req_ids The site's requirement ids.
## @return ({requirement: issues}, issues linked to none).
## @version 1
## @req REQ-DDB-WIKI-028
def link_issues(
    issues: list[Issue], req_ids: list[str]
) -> tuple[dict[str, list[Issue]], list[Issue]]:
    """AN ID MATCHES WHOLE: `REQ-W-0011` does not link `REQ-W-001` — the character after the id
    may not continue it.

    @brief Link.
    @return Linked and unlinked.
    """
    linked: dict[str, list[Issue]] = {}
    unlinked = []
    patterns = {r: re.compile(rf"(?<![\w-]){re.escape(r)}(?![\w])") for r in req_ids}
    for issue in issues:
        text = f"{issue.title}\n{issue.body}"
        hits = [
            r
            for r, pattern in patterns.items()
            if f"req:{r}" in issue.labels or pattern.search(text)
        ]
        for r in hits:
            linked.setdefault(r, []).append(issue)
        if not hits:
            unlinked.append(issue)
    return linked, unlinked


## @brief One GitHub REST row as an issue.
## @param row The row.
## @return The issue.
## @version 1
## @utility
def _gh_issue(row: dict) -> Issue:
    """@brief Convert. @return Issue."""
    return Issue(
        str(row["number"]),
        str(row.get("title") or ""),
        str(row.get("body") or ""),
        tuple(str(label["name"]) for label in row.get("labels") or []),
        str(row.get("html_url") or ""),
        str(row.get("state") or ""),
    )


## The most pages of 100 a GitHub listing follows; reaching it is DISCLOSED (`truncated`, D14).
_MAX_PAGES = 50


## @brief Follow a paged listing of 100 per page until a short page or the page cap.
## @param get_page Fetches one page by its 1-based number.
## @param max_pages The cap.
## @return (rows, whether the cap was reached with pages left).
## @version 1
## @req REQ-DDB-WIKI-028
def fetch_pages(get_page: Any, max_pages: int) -> tuple[list[dict], bool]:
    """R5-CFG D14 (2.0.0): the loop stopped at its cap and returned what it had with NO disclosure,
    so a tracker with more open issues than the cap read as having exactly that many — the
    "absence is not emptiness" failure. The cap stays; reaching it is now reported.

    @brief Page through a listing.
    @return Rows and the truncation flag.
    """
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        rows = get_page(page) or []
        out += rows
        if len(rows) < 100:
            return out, False
    return out, True


_WIQL = (
    "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project AND "
    "[System.State] NOT IN ('Closed', 'Done', 'Removed', 'Resolved')"
)
_ADO_FIELDS = "System.Title,System.Description,System.Tags,System.State"
