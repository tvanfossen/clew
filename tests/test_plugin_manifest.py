# SPDX-License-Identifier: MIT
"""The Claude Code plugin manifest must agree with the package it installs.

`.claude-plugin/plugin.json` shipped for weeks declaring `name`, `version`, `description`,
`author`, `homepage` and `license` — and NO `mcpServers` key, no plugin-root `.mcp.json`,
and no marketplace manifest. It therefore registered zero MCP servers. Worse than absent:
it looks installable as a plugin and installs nothing, which produces the least actionable
bug report a consumer can file.

It was also referenced by nothing — no test, no CI step, no code — so its `version` was a
THIRD version string with no mechanism keeping it in step with `pyproject.toml`. The release
workflow checks the git tag against the built wheel and never reads this file.

Both assertions below are structural rather than value comparisons against a literal: a
hardcoded "0.5.0" here would itself become a fourth place to forget.

@brief Tests for the plugin manifest's agreement with pyproject.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

## THROUGH THE PACKAGE'S OWN SHIM, not a bare `import tomllib`. This module's floor is 3.10 and
## `tomllib` is stdlib only from 3.11, so the bare import broke collection of this whole file on
## the oldest supported interpreter — and `tomlcompat` exists precisely to stop that, its
## docstring recording an earlier instance where one call site had the fallback and another did
## not. A test is a call site.
import clew_hook
from clew.tomlcompat import require_toml_module

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"


##
# @brief Load the plugin manifest.
# @return Parsed manifest.
# @version 1
def _manifest() -> dict:
    """@brief Load the plugin manifest. @return Parsed manifest. @version 1"""
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


##
# @brief Load pyproject.
# @return Parsed pyproject.
# @version 1
def _pyproject() -> dict:
    """@brief Load pyproject. @return Parsed pyproject. @version 1"""
    return require_toml_module().loads(PYPROJECT.read_text(encoding="utf-8"))


## @brief The manifest version tracks the package version.
## @return None.
## @version 1
def test_plugin_version_matches_the_package_version() -> None:
    """@brief Manifest and package versions agree. @return None. @version 1"""
    assert _manifest()["version"] == _pyproject()["project"]["version"], (
        "the plugin manifest declares a version the package does not — it is referenced by "
        "nothing else in the repo, so nothing but this assertion keeps the two in step"
    )


## @brief The manifest actually registers this package's MCP server.
## @return None.
## @version 1
def test_plugin_manifest_registers_the_mcp_server_by_its_console_script() -> None:
    """THE DEFECT THIS FILE EXISTS FOR: the manifest declared no `mcpServers` at all, so
    installing the plugin gave a user everything except the server that is the entire point.

    The command is checked against `[project.scripts]` rather than a literal, so renaming the
    console script fails here instead of failing silently for whoever installs the plugin next.
    The schema permits either a path string or an inline object; this asserts on whichever
    shape is present rather than mandating one.

    @brief The manifest registers the server, under a real console-script name.
    @return None.
    @version 1
    """
    servers = _manifest().get("mcpServers")
    assert servers, "a plugin manifest with no mcpServers registers nothing and installs nothing"
    if isinstance(servers, str):
        assert (MANIFEST.parent / servers).exists(), "mcpServers names a file that does not exist"
        return

    scripts = set(_pyproject()["project"]["scripts"])
    commands = {entry.get("command") for entry in servers.values()}
    assert commands <= scripts, (
        f"the manifest launches {sorted(commands)}, which this package does not install; "
        f"declared console scripts are {sorted(scripts)}"
    )


## @brief No module may import `tomllib` bare — the package floor is older than that stdlib.
## @return None.
## @version 1
def test_no_module_imports_tomllib_bare() -> None:
    """THIRD-OCCURRENCE PREVENTION, and the first two are on the record. `tomlcompat`'s own
    docstring describes call sites that had diverged — one carried the 3.10 fallback and one
    imported `tomllib` bare inside an `except` broad enough to swallow the ImportError and return
    an empty document. Then this very test module did it again and broke collection of itself on
    3.10, which CI caught and local development did not, because the dev venv is newer.

    THE SHAPE IS WHY A COMMENT WOULD NOT HAVE HELPED. A bare `import tomllib` is correct on the
    interpreter every developer runs and fails only on the oldest supported one, so it passes
    review, passes locally, and fails in CI on a matrix leg nobody reads until it goes red. A
    check is cheaper than the habit.

    `tomlcompat` itself is exempt: it IS the fallback, and it must import both names to offer one.

    @brief Only the compatibility shim imports tomllib directly.
    @return None.
    @version 1
    """
    import re
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert tracked, "git listed no Python files — the check would pass vacuously"

    bare = re.compile(r"^\s*import\s+tomllib\b", re.MULTILINE)
    offenders = [
        path
        for path in tracked
        if not path.endswith("tomlcompat.py")
        and bare.search((REPO_ROOT / path).read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"these import `tomllib` directly and will fail to import on Python 3.10, the declared "
        f"floor: {offenders}. Use `clew.tomlcompat.require_toml_module()`."
    )


## @brief The marketplace catalog must exist and agree with the plugin manifest.
## @return None.
## @version 1
def test_marketplace_catalog_agrees_with_the_plugin_manifest() -> None:
    """A PLUGIN WITHOUT A MARKETPLACE CANNOT BE INSTALLED, which is the gap this closes. The
    documented distribution model is two files: `.claude-plugin/plugin.json` describes the plugin,
    and `.claude-plugin/marketplace.json` is the CATALOG a user adds. The install flow is
    `/plugin marketplace add <repo>` then `/plugin install <plugin>@<marketplace>`, so a repo
    carrying only a plugin manifest is discoverable by nobody — it looks installable and is not,
    the same shape as the manifest that registered zero MCP servers.

    `source: "./"` is the documented spelling for a repository that IS the plugin, rather than a
    marketplace holding plugins in subdirectories.

    NO `version` IN THE CATALOG ENTRY, asserted rather than merely omitted. The reference says a
    version set EITHER here or in `plugin.json` pins the plugin; setting it in both makes a second
    place to forget, which is the defect the first test in this file exists for.

    @brief The catalog exists, names this plugin, and does not duplicate its version.
    @return None.
    @version 1
    """
    catalog_path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert catalog_path.is_file(), (
        "without .claude-plugin/marketplace.json there is nothing for `/plugin marketplace add` "
        "to read, so the plugin cannot be installed by anyone"
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    for key in ("name", "owner", "plugins"):
        assert key in catalog, f"the marketplace schema requires {key!r}"
    assert catalog["plugins"], "a catalog listing no plugins distributes nothing"

    manifest_name = _manifest()["name"]
    entries = {entry["name"]: entry for entry in catalog["plugins"]}
    assert manifest_name in entries, (
        f"the catalog lists {sorted(entries)} but the plugin manifest calls itself "
        f"{manifest_name!r}; users install by the catalog name and would get nothing"
    )
    entry = entries[manifest_name]
    assert entry["source"] == "./", (
        "this repository IS the plugin, so the documented source spelling is './' — a "
        "subdirectory path would resolve to a directory with no plugin.json in it"
    )
    assert "version" not in entry, (
        "version is already declared in plugin.json; declaring it in both pins the plugin from "
        "two places and makes one of them silently authoritative"
    )


## @brief Field TYPES in both manifests must match what the plugin installer validates.
## @return None.
## @version 1
def test_manifest_field_types_match_the_published_schema() -> None:
    """THE INSTALLER REJECTED A MANIFEST THIS FILE HAD ALREADY PASSED. `author` was the string
    "tvanfossen"; the schema requires an object with a `name`. `/plugin install` refused with
    "author: Invalid input: expected object, received string", and the two tests above were green
    throughout because they check the version and the server command and nothing else.

    So the gap was never the fields we edited — it was the ones we did not. Types are asserted
    here for every field either manifest actually sets, which is the set an installer will parse.

    @brief Manifest field types match the schema the installer enforces.
    @return None.
    @version 1
    """
    manifest = _manifest()
    catalog = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())

    for label, doc in (("plugin.json", manifest), ("marketplace.json", catalog)):
        assert isinstance(doc.get("name"), str), f"{label}: name must be a string"

    ## `author` and `owner` are OBJECTS with a required `name`, in both files. The string form
    ## parses as JSON and fails validation, which is why valid-JSON is not the check that matters.
    for label, doc, field in (
        ("plugin.json", manifest, "author"),
        ("marketplace.json", catalog, "owner"),
    ):
        value = doc.get(field)
        assert isinstance(value, dict), (
            f"{label}: {field} must be an OBJECT, not {type(value).__name__} — the installer "
            f"rejects the string form outright"
        )
        assert isinstance(value.get("name"), str), f"{label}: {field}.name is required"

    for entry in catalog["plugins"]:
        author = entry.get("author")
        if author is not None:
            assert isinstance(author, dict) and isinstance(author.get("name"), str), (
                "marketplace.json: a plugin entry's author has the same object shape"
            )


## @brief No catalog entry may turn off strict mode while plugin.json owns the components.
## @return None.
## @version 1
def test_no_catalog_entry_disables_strict_mode() -> None:
    """A ONE-WORD CHANGE THAT WOULD SILENTLY UNREGISTER THE SERVER. `strict` is a per-entry
    field defaulting to `true`, and `true` means `plugin.json` is the authority for the
    plugin's components. `strict: false` makes the MARKETPLACE ENTRY the entire definition —
    and this catalog's entry declares no `mcpServers` at all, because the plugin manifest is
    where they live.

    So flipping it would leave a plugin that installs, reports success, and registers nothing:
    the same failure this file's second test exists for, reached from the opposite direction
    and needing no edit to `plugin.json` to happen.

    Asserted as ABSENT-OR-TRUE rather than required-present. The default is already what this
    plugin wants, and writing it out would add a second place to keep in step for no gain —
    which is the defect the first test in this file exists for.

    @brief No entry sets strict false while plugin.json owns the components.
    @return None.
    @version 1
    """
    catalog = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    for entry in catalog["plugins"]:
        assert entry.get("strict", True) is True, (
            f"catalog entry {entry.get('name')!r} sets strict false, which makes this entry the "
            f"whole plugin definition — and it declares no mcpServers, so the server would stop "
            f"being registered while the install still reported success"
        )
        assert not (set(entry) & {"mcpServers", "commands", "agents", "hooks", "skills"}), (
            "components belong in plugin.json, which is authoritative under strict mode; "
            "declaring them here too makes one of the two silently win"
        )


## @brief The plugin's MCP server must be exempt from tool-search deferral.
## @return None.
## @version 1
def test_the_manifest_exempts_the_server_from_tool_search_deferral() -> None:
    """gh#7's manifest half. `alwaysLoad: true` on the server entry makes every tool from it load
    at session start instead of arriving as a DEFERRED tool that needs a `ToolSearch` round trip
    before it can be called.

    BOTH HALVES ARE DECLARED BECAUSE NEITHER CAN BE VERIFIED HERE. The server also stamps
    `anthropic/alwaysLoad` into each tool's `_meta`, which travels over the wire; this covers a
    client that decides before the server is asked. Either alone is a single point of failure, and
    this process cannot observe which one a real client honoured.

    @brief The manifest's server entry sets alwaysLoad.
    @return None.
    @version 1
    """
    servers = _manifest()["mcpServers"]
    assert isinstance(servers, dict), "the object form is required to carry alwaysLoad"
    for name, entry in servers.items():
        assert entry.get("alwaysLoad") is True, (
            f"server {name!r} does not set alwaysLoad, so its tools arrive deferred — one "
            f"ToolSearch round trip behind grep, which is what gh#7 measured the cost of"
        )


## @brief The shipped hook must be the packaged console script, never a shell command line.
## @return None.
## @version 1
def test_the_plugin_hook_is_a_packaged_console_script() -> None:
    """A HOOK IS AN INVISIBLE EXECUTABLE ON A CONSUMER'S MACHINE, so what the plugin asks to run
    matters as much as what that program does. A shell command line in the manifest would put an
    unreviewed string on the far side of a shell, where quoting and expansion are somebody else's
    problem; a console script is the same installed package the server already is, reviewable in
    this repository.

    Asserted against `[project.scripts]` rather than a literal, so renaming the entry point fails
    here instead of failing silently for whoever installs the plugin next — the same discipline
    the mcpServers check above uses.

    @brief The hook command is a declared console script.
    @return None.
    @version 1
    """
    hooks_path = REPO_ROOT / "hooks" / "hooks.json"
    assert hooks_path.is_file(), "the plugin ships no hooks/hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))

    scripts = set(_pyproject()["project"]["scripts"])
    ## The only arguments the manifest may pass. They are how the hook learns WHICH tool ran
    ## without reading its untrusted stdin, so they are part of the security design and are
    ## enumerated here rather than waved through — an unknown flag reaching the hook would mean
    ## the manifest and the program disagree about what is being said.
    allowed_args = {clew_hook.USED_FLAG}
    commands = [
        entry["command"]
        for group in hooks["hooks"].values()
        for matcher in group
        for entry in matcher["hooks"]
    ]
    assert commands, "a hooks.json registering nothing is worse than absent"
    for command in commands:
        for metachar in ("|", ";", "&", "$", "`", ">", "<", "\n"):
            assert metachar not in command, (
                f"{command!r} contains {metachar!r} — no shell metacharacter may reach a "
                f"consumer's machine from this manifest"
            )
        program, *args = command.split()
        assert program in scripts, (
            f"the hook runs {program!r}, which this package does not install; declared console "
            f"scripts are {sorted(scripts)}"
        )
        unknown = set(args) - allowed_args
        assert not unknown, (
            f"{command!r} passes {sorted(unknown)}, which the hook does not define. The manifest's "
            f"arguments are how the hook learns which tool ran; an unrecognised one means the two "
            f"have drifted."
        )


## @brief The hook must be registered on PostToolUse only, never on a blocking event.
## @return None.
## @version 1
def test_the_hook_is_registered_only_on_a_non_blocking_event() -> None:
    """`PreToolUse` can DENY a tool call. This hook exists to add one line of context, and a
    context-adding component registered on a gate is one bug away from blocking a consumer's
    `Grep` — a failure mode entirely out of proportion to what it is for.

    `PostToolUse` cannot block: the tool has already run.

    @brief Only non-blocking events carry this hook.
    @return None.
    @version 1
    """
    hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    blocking = {"PreToolUse", "UserPromptSubmit", "Stop", "SubagentStop", "PreCompact"}
    registered = set(hooks["hooks"])
    assert registered <= {"PostToolUse"}, (
        f"the hook is registered on {sorted(registered - {'PostToolUse'})}; only PostToolUse is "
        f"non-blocking, and {sorted(blocking & registered)} can interfere with the consumer's work"
    )


## @brief Both halves of the counter must be registered, and their matchers must not overlap.
## @return None.
## @version 1
def test_both_halves_of_the_pressure_counter_are_registered() -> None:
    """MEASURED LIVE, ON A SHIPPED ARTIFACT. A `hooks.json` carrying only the search matcher
    passes every other test in this file — the command is a declared console script, it sits on
    a non-blocking event, it holds no metacharacter — and it silently breaks the hook, because
    the counter then only ever RISES. A session that used the index on every single call would
    escalate to speaking on every call, which is the precise opposite of the policy. That
    artifact reached a pushed release branch and was found by running the product, not the suite.

    THE MATCHERS ARE TESTED AS REGEXES AGAINST REAL TOOL NAMES, not compared to literals. Both
    install shapes must credit: a directly-registered server serves `mcp__clew__dossier` while a
    plugin-scoped one serves `mcp__plugin_clew_clew__dossier`. A matcher of `mcp__clew__.*` looks
    obviously right, matches the first, and misses the second — so every plugin user, which is
    everyone this manifest is for, would earn no credit at all.

    NON-OVERLAP IS THE OTHER HALF. A matcher that caught both a search and a clew call would
    make one Bash call record a miss AND a credit, and the counter would measure nothing.

    @brief The search and credit matchers are both present and disjoint.
    @return None.
    @version 1
    """
    import re

    hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    registrations = [
        (matcher["matcher"], entry["command"])
        for group in hooks["hooks"].values()
        for matcher in group
        for entry in matcher["hooks"]
    ]

    credit = [pattern for pattern, command in registrations if clew_hook.USED_FLAG in command]
    search = [pattern for pattern, command in registrations if clew_hook.USED_FLAG not in command]
    assert credit, (
        f"no registration passes {clew_hook.USED_FLAG!r}, so using the index never subtracts from "
        f"the pressure counter and the hook escalates no matter how the session behaves"
    )
    assert search, "no registration counts searches, so the hook has nothing to escalate on"

    ## Both spellings a real client serves. Neither is hypothetical: this repository is consumed
    ## as a plugin, and `clew init` registers the same server directly.
    clew_tools = ("mcp__clew__dossier", "mcp__plugin_clew_clew__dossier")
    searches = ("Bash", "Grep", "Glob", "Read")

    for pattern in credit:
        for tool in clew_tools:
            assert re.match(pattern, tool), (
                f"credit matcher {pattern!r} does not match {tool!r} — that install shape would "
                f"earn no credit, so the index could be used constantly and still escalate"
            )
        for tool in searches:
            assert not re.match(pattern, tool), (
                f"credit matcher {pattern!r} also matches {tool!r}, so a search would credit "
                f"itself and the counter would measure nothing"
            )

    for pattern in search:
        for tool in searches:
            assert re.match(pattern, tool), (
                f"search matcher {pattern!r} does not match {tool!r}, so that tool adds no "
                f"pressure and the hook stays silent through exactly the sessions it is for"
            )
        for tool in clew_tools:
            assert not re.match(pattern, tool), (
                f"search matcher {pattern!r} also matches {tool!r}, so an index call would "
                f"count as a miss against itself"
            )
