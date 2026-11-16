# SPDX-License-Identifier: MIT
"""Issue links: a prefilled "raise an issue" URL for GitHub or Azure DevOps (round 3, P1d).

Owner 2026-11-15: issues link to requirements ALL THREE WAYS — the id in the title, a `req:<ID>`
label (an ADO tag), and a marker line `clew-req: <ID>` in the body — so whichever one a tracker
keeps, the link survives. The page only carries a URL: nothing is sent anywhere until a person
opens it and submits the tracker's own form.

The tracker is DECLARED (`wiki.issues: {github: owner/repo}` or `{ado: org/project}`), or read
from the repository's `origin` remote; an unrecognised host gives NO link — a guessed tracker
would file issues somewhere nobody reads.

@brief Prefilled issue URLs and tracker discovery.
@version 1
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode

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
