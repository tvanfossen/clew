# SPDX-License-Identifier: MIT
"""Hosting the wiki from CI (round 3, P5c).

Owner 2026-11-15: serve the wiki directly on GitHub (replacing entropic's doxygen-to-Pages
workflow) or Azure DevOps. Two pieces ship in this repository:

  * a COMPOSITE ACTION (`.github/actions/wiki`) that installs clew at a pinned release, indexes
    the checkout and builds the wiki (HTML for Pages, or Markdown for a GitHub wiki), and outputs
    the built directory — the caller keeps its own upload and deploy steps;
  * an AZURE PIPELINES TEMPLATE (`templates/azure-pipelines-wiki.yml`) that builds the Markdown
    wiki in the ADO flavour and pushes it to a code wiki with the job's own token.

Both pin clew to this release (read from pyproject, so a version bump that forgets them fails
here), and every action this repository uses — workflows and the action alike — is pinned by
commit SHA, the supply-chain rule docs/SECURITY.md states, now enforced rather than remembered.

@brief Tests for the CI hosting pieces.
@version 1
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
_SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _version() -> str:
    from clew.tomlcompat import require_toml_module

    return require_toml_module().loads((REPO / "pyproject.toml").read_text())["project"]["version"]


def _uses(doc: object) -> list[str]:
    """Every `uses:` value anywhere in a parsed YAML document."""
    found: list[str] = []
    if isinstance(doc, dict):
        for key, value in doc.items():
            if key == "uses" and isinstance(value, str):
                found.append(value)
            found += _uses(value)
    elif isinstance(doc, list):
        for item in doc:
            found += _uses(item)
    return found


def test_every_action_is_pinned_by_commit_sha() -> None:
    """@brief Workflows and the composite action: `owner/action@<40-hex sha>` or a local path."""
    files = [
        *(REPO / ".github" / "workflows").glob("*.yml"),
        *(REPO / ".github" / "actions").rglob("action.yml"),
    ]
    assert any("actions" in f.parts for f in files), "the composite action must exist"
    loose = [
        (f.relative_to(REPO).as_posix(), use)
        for f in files
        for use in _uses(yaml.safe_load(f.read_text()))
        if not use.startswith("./") and not _SHA.match(use)
    ]
    assert loose == [], f"actions not pinned by commit SHA: {loose}"


def test_the_composite_action_builds_the_wiki_at_this_release() -> None:
    """@brief Composite; clew at this release with the wiki extra; HTML or Markdown; the site out."""
    action = yaml.safe_load((REPO / ".github" / "actions" / "wiki" / "action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    inputs = action["inputs"]
    assert inputs["version"]["default"] == _version()
    assert {"format", "flavor", "out", "config", "audience"} <= set(inputs)
    runs = "\n".join(str(s.get("run", "")) for s in action["runs"]["steps"])
    assert "clew-trace[wiki]==${{ inputs.version }}" in runs
    assert "clew wiki build" in runs and "--format" in runs
    assert "site" in action["outputs"]


def test_the_azure_template_pushes_the_ado_flavour_to_a_code_wiki() -> None:
    """THE JOB'S OWN TOKEN, NEVER PRINTED: it reaches git through an extra header, not a URL that
    would land in the log.

    @brief Azure Pipelines template.
    """
    text = (REPO / "templates" / "azure-pipelines-wiki.yml").read_text()
    doc = yaml.safe_load(text)
    params = {p["name"]: p for p in doc["parameters"]}
    assert params["clewVersion"]["default"] == _version()
    assert {"wikiRepository", "wikiBranch"} <= set(params)
    assert "--format markdown --flavor ado" in text
    assert "System.AccessToken" in text and "http.extraheader" in text
    assert not re.search(r"https://[^\s]*\$\(System\.AccessToken\)", text)
