# SPDX-License-Identifier: MIT
"""Issues, read side (round 3, P3a): GitHub and Azure DevOps over stdlib REST, linked to requirements.

Owner 2026-11-15: open issues link back to requirements ALL THREE WAYS — the requirement id in
the title or body, a `req:<ID>` label (an ADO tag), a `clew-req: <ID>` marker line. Fetching is
OPT-IN (`wiki.issues.fetch: true`): a build never reaches the network unless the repository says
so, and a failed fetch is stated on the page, never a crash and never an empty list that reads
"no issues".

Every test here answers HTTP from canned fixtures through an injected opener — no network.

@brief Tests for issue providers, linking and their place on the site.
@version 1
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from clew.wiki.issues import AdoIssues, GitHubIssues, Issue, link_issues


class _Fake:
    """An opener answering (method, url) from canned JSON, recording every request."""

    def __init__(self, routes: dict[tuple[str, str], object]) -> None:
        self.routes = routes
        self.seen: list[tuple[str, str, dict, bytes | None]] = []

    def __call__(self, request, timeout: float = 0):  # noqa: ANN001
        key = (request.get_method(), request.full_url)
        self.seen.append((*key, dict(request.header_items()), request.data))
        if key not in self.routes:
            raise AssertionError(f"unexpected request {key}")
        return _Response(json.dumps(self.routes[key]).encode())


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *exc: object) -> None:
        return None


_GH = "https://api.github.com/repos/acme/demo/issues?state=open&per_page=100&page="


def test_github_lists_open_issues_across_pages_without_pull_requests() -> None:
    """@brief GitHub: pages followed until a short page; pull requests are not issues."""
    page1 = [
        {
            "number": i,
            "title": f"t{i}",
            "body": "",
            "labels": [{"name": "bug"}],
            "html_url": f"u{i}",
            "state": "open",
        }
        for i in range(100)
    ]
    page1[0]["pull_request"] = {"url": "x"}
    page2 = [
        {
            "number": 500,
            "title": "last",
            "body": None,
            "labels": [],
            "html_url": "u500",
            "state": "open",
        }
    ]
    fake = _Fake({("GET", _GH + "1"): page1, ("GET", _GH + "2"): page2})
    issues = GitHubIssues("acme/demo", token="tok", opener=fake).list_open()
    assert len(issues) == 100 and issues[-1] == Issue("500", "last", "", (), "u500", "open")
    assert issues[0].labels == ("bug",)
    assert fake.seen[0][2]["Authorization"] == "Bearer tok"


def test_ado_lists_open_work_items_through_wiql() -> None:
    """@brief Azure DevOps: a WIQL query for open items, then one batch read of their fields."""
    base = "https://dev.azure.com/org/proj/_apis/wit"
    fake = _Fake(
        {
            ("POST", f"{base}/wiql?api-version=7.0"): {"workItems": [{"id": 7}, {"id": 9}]},
            (
                "GET",
                f"{base}/workitems?ids=7,9&fields=System.Title,System.Description,System.Tags,System.State&api-version=7.0",
            ): {
                "value": [
                    {
                        "id": 7,
                        "fields": {
                            "System.Title": "A",
                            "System.Tags": "req:REQ-1; ui",
                            "System.State": "Active",
                        },
                    },
                    {
                        "id": 9,
                        "fields": {
                            "System.Title": "B",
                            "System.Description": "<p>x</p>",
                            "System.State": "New",
                        },
                    },
                ]
            },
        }
    )
    issues = AdoIssues("org/proj", token="pat", opener=fake).list_open()
    assert [i.id for i in issues] == ["7", "9"] and issues[0].labels == ("req:REQ-1", "ui")
    assert issues[0].url == "https://dev.azure.com/org/proj/_workitems/edit/7"
    auth = fake.seen[0][2]["Authorization"]
    assert auth == "Basic " + base64.b64encode(b":pat").decode()


def test_issues_link_to_requirements_three_ways_and_never_by_prefix() -> None:
    """THE ID IN TITLE OR BODY, a `req:` label, a `clew-req:` marker line; `REQ-W-0011` does not
    link `REQ-W-001`.

    @brief Linking.
    """
    issues = [
        Issue("1", "REQ-W-001 is slow", "", (), "u1", "open"),
        Issue("2", "Crash", "", ("req:REQ-X-001",), "u2", "open"),
        Issue("3", "Other", "details\nclew-req: REQ-W-002\n", (), "u3", "open"),
        Issue("4", "REQ-W-0011 only", "", (), "u4", "open"),
        Issue("5", "Unrelated", "", (), "u5", "open"),
    ]
    linked, unlinked = link_issues(issues, ["REQ-W-001", "REQ-W-002", "REQ-X-001"])
    assert [i.id for i in linked["REQ-W-001"]] == ["1"]
    assert [i.id for i in linked["REQ-X-001"]] == ["2"]
    assert [i.id for i in linked["REQ-W-002"]] == ["3"]
    assert [i.id for i in unlinked] == ["4", "5"]


def test_create_and_label_carry_the_id_three_ways() -> None:
    """@brief Write side (used by `clew wiki serve`): create with title, label and marker line."""
    gh = _Fake(
        {("POST", "https://api.github.com/repos/acme/demo/issues"): {"number": 3, "html_url": "u3"}}
    )
    made = GitHubIssues("acme/demo", token="t", opener=gh).create("REQ-1", "Title", "Body")
    sent = json.loads(gh.seen[0][3])
    assert (
        made == ("3", "u3")
        and sent["labels"] == ["req:REQ-1"]
        and "clew-req: REQ-1" in sent["body"]
    )
    assert sent["title"].startswith("REQ-1")
    ado = _Fake(
        {
            ("POST", "https://dev.azure.com/org/proj/_apis/wit/workitems/$Issue?api-version=7.0"): {
                "id": 4
            }
        }
    )
    made = AdoIssues("org/proj", token="p", opener=ado).create("REQ-1", "Title", "Body")
    patch = {op["path"]: op["value"] for op in json.loads(ado.seen[0][3])}
    assert made == ("4", "https://dev.azure.com/org/proj/_workitems/edit/4")
    assert (
        patch["/fields/System.Tags"] == "req:REQ-1"
        and "clew-req: REQ-1" in patch["/fields/System.Description"]
    )
    assert ado.seen[0][2]["Content-type"] == "application/json-patch+json"


# --- on the site ----------------------------------------------------------------------------------

from tests.test_wiki_site import _WIKI, repo  # noqa: E402, F401  (module fixture reused)


def _build(repo, tmp_path: Path, monkeypatch, provider) -> dict[str, str]:  # noqa: ANN001, F811
    from clew.wiki import issues as mod
    from clew.wiki.build import build_wiki

    monkeypatch.setattr(mod, "provider_for", lambda target, opener=None: provider)
    config = tmp_path / "wiki.yaml"
    config.write_text(
        _WIKI.replace("issues: {github: acme/demo}", "issues: {github: acme/demo, fetch: true}")
    )
    html = build_wiki(repo[0], repo[1], tmp_path / "out", config_path=config)
    return {p.name: p.read_text() for p in html.glob("*.html")}


class _Provider:
    def __init__(self, issues: list[Issue] | None = None, error: str = "") -> None:
        self.issues, self.error = issues, error

    def list_open(self) -> list[Issue]:
        if self.error:
            raise OSError(self.error)
        return self.issues or []


def test_open_issues_reach_the_requirement_and_its_group(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@brief A requirement's modal and row list its open issues; unlinked ones are listed apart."""
    provider = _Provider(
        [
            Issue("12", "REQ-W-001 loads twice", "", (), "https://example.invalid/i/12", "open"),
            Issue("13", "Docs typo", "", (), "https://example.invalid/i/13", "open"),
        ]
    )
    page = _build(repo, tmp_path, monkeypatch, provider)["requirements.html"]
    body = page[page.index('<template id="modal-req-REQ-W-001"') :]
    body = body[: body.index("</template>")]
    assert 'href="https://example.invalid/i/12"' in body and "#12" in body
    row = page[page.index('<tr data-group="REQ-W"') :].split("</tr>")[0]
    assert "#12" in row
    assert "Docs typo" in page[page.index("Not linked to a requirement") :]


def test_a_failed_fetch_is_said_not_shown_as_no_issues(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@brief A fetch that fails leaves the site built and says issues were not fetched, and why."""
    page = _build(repo, tmp_path, monkeypatch, _Provider(error="network down"))["requirements.html"]
    assert "Issues were not fetched" in page and "network down" in page
