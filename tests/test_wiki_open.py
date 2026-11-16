# SPDX-License-Identifier: MIT
"""One-click entry to the wiki (round 3, P5a).

Owner 2026-11-15: "need a one click entry into the wiki". `clew wiki open`:

  * when the MCP server's wiki hub is running (its `wiki.json` names a live process), opens the
    hub's page for this repository — live, rebuilt as the index refreshes;
  * otherwise builds the static site where the hub keeps it (beside the index) and opens it as a
    file — reading never needs a server;
  * always prints the URL it opened; `--no-browser` opens nothing.

The plugin ships the same as its `/wiki` command, launched through uv at the plugin's pinned
release like the MCP server.

@brief Tests for `clew wiki open` and the plugin command.
@version 1
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def test_without_a_hub_the_static_site_is_built_and_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief No hub: build beside the index, open as a file."""
    from clew.mcp_server.state import target_for
    from clew.wiki import open_command

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("CLEW_STATE_HOME", str(tmp_path / "state"))
    built: list[Path] = []

    def fake_build(repo_root: Path, db: Path, out: Path, **_kw: object) -> Path:
        built.append(out)
        (out / "html").mkdir(parents=True, exist_ok=True)
        (out / "html" / "index.html").write_text("site")
        return out / "html"

    monkeypatch.setattr(open_command, "build_wiki", fake_build)
    monkeypatch.setattr(open_command, "_ensure_index", lambda repo_root, db: None)
    assert open_command.open_main(["--repo-root", str(repo), "--no-browser"]) == 0
    target = target_for(repo, tmp_path / "state")
    assert built == [Path(target.db_path).parent / "wiki"]
    assert (
        capsys.readouterr().out.strip()
        == (Path(target.db_path).parent / "wiki" / "html" / "index.html").as_uri()
    )


def test_a_running_hub_is_opened_instead_and_a_dead_one_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief A live hub's page for this repository; a record left by a dead process is ignored."""
    from clew.mcp_server.state import target_for
    from clew.wiki import open_command

    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "state"
    home.mkdir()
    monkeypatch.setenv("CLEW_STATE_HOME", str(home))
    (home / "wiki.json").write_text(
        json.dumps({"url": "http://127.0.0.1:4242/?t=tok", "pid": os.getpid()})
    )
    monkeypatch.setattr(
        open_command, "build_wiki", lambda *a, **k: pytest.fail("no build with a hub")
    )
    assert open_command.open_main(["--repo-root", str(repo), "--no-browser"]) == 0
    slug = target_for(repo, home).slug
    assert capsys.readouterr().out.strip() == f"http://127.0.0.1:4242/r/{slug}/?t=tok"
    (home / "wiki.json").write_text(
        json.dumps({"url": "http://127.0.0.1:4242/?t=tok", "pid": 999999999})
    )
    assert open_command._live_hub(home) is None


def test_the_plugin_ships_a_wiki_command_at_its_pinned_release() -> None:
    """THE SAME PIN AS THE MCP SERVER, read from pyproject — a command launching another
    release than the server would build a site with different code. The plugin's own
    description names its tools as they are in 2.0.0.

    @brief Plugin command and description.
    """
    from clew.tomlcompat import require_toml_module

    version = require_toml_module().loads((REPO / "pyproject.toml").read_text())["project"][
        "version"
    ]
    command = (REPO / "commands" / "wiki.md").read_text()
    assert command.startswith("---\n") and "description:" in command.split("---")[1]
    assert f"clew-trace[wiki]=={version}" in command and "clew wiki open" in command
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert "three tools" in manifest["description"] and "four tools" not in manifest["description"]
