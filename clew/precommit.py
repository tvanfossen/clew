# SPDX-License-Identifier: MIT
"""Read what a repo declares about doxygen-guard in its pre-commit config.

Every repo that adopts doxygen-guard states so in its `.pre-commit-config.yaml`,
and that entry answers two questions nothing else can: which RELEASE of the guard
the repo pins (`pinned_guard_rev`) and where the repo keeps the guard config it
obeys (`discover_guard_config`, via the hook's `--config` arg).

This module used to compile a third thing out of that hook — its `files:` /
`exclude:` regexes, as a queryable filter over the doxygen MANDATE. That filter
is GONE, along with the guard tier of index-scope derivation it fed. INDEX scope
is not GATE scope: the gate says what must be DOCUMENTED, the index says what
should be REASONABLE-ABOUT, and deriving the second from the first made a repo
loosen its quality bar to widen its graph. With the tier removed the filter had
no consumer, so it is deleted rather than kept warm.

The hook is located by its ID, never by repo URL or position: an adopting repo
may pull doxygen-guard from its upstream URL or run it as a `repo: local`
system hook, and both are equally valid declarations.

@brief pre-commit doxygen-guard declaration parsing.
@version 2
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ._common import logger

PRECOMMIT_CONFIG_NAME = ".pre-commit-config.yaml"
GUARD_HOOK_ID = "doxygen-guard"

## The conventional root-level name of doxygen-guard's own config. A repo that keeps
## it elsewhere DECLARES that location in the hook's `args:` — see
## `discover_guard_config`, which is the single answer to "where is this repo's
## guard config" for every consumer.
GUARD_CONFIG_NAME = ".doxygen-guard.yaml"

## The flag a pre-commit hook uses to name a non-root guard config. This is
## doxygen-guard's OWN CLI spelling, not a target repo's convention, so reading it
## is the same kind of default as knowing the hook's id.
_CONFIG_FLAG = "--config"

## Directories a repo may keep its guard config in when it is not at the root.
## Tool-config conventions, not any one target's layout — and unlike the root the
## file there is conventionally UNdotted, so both spellings are tried.
_GUARD_CONFIG_DIRS = ("conf", "config", ".config")
_GUARD_CONFIG_NAMES = ("doxygen-guard.yaml", GUARD_CONFIG_NAME)

## Provenance of a discovered guard config, reported so a build log can always say
## WHICH config was used and HOW it was found — the same contract `DerivedScope`
## carries for the index scope.
##
## THIS ONE USED TO READ `--guard-config`, AND THAT FLAG NO LONGER EXISTS. The build CLI
## collapsed to six arguments and `--guard-config` was DELETED in favour of the discovery
## below — this function's own docstring is the argument for that: discovery works from the
## repo root alone, so a target keeping its config in `conf/` is indexable through both entry
## points with nothing passed. A provenance string naming a deleted flag would send a reader
## hunting an argument that is not there, which is this repo's recorded "error message that
## names a nonexistent tool" shape. The `explicit=` parameter survives as a programmatic seam
## and is reached by no shipped entry point.
GUARD_SOURCE_EXPLICIT = "stated by the caller"
GUARD_SOURCE_ROOT = "repo root"
GUARD_SOURCE_HOOK_ARGS = "pre-commit hook args"
GUARD_SOURCE_CONVENTIONAL = "conventional directory"
GUARD_SOURCE_NONE = "not found"


## @brief Locate the doxygen-guard hook in a parsed pre-commit config.
## @param data Parsed `.pre-commit-config.yaml` mapping.
## @return The hook mapping whose id is `doxygen-guard`, else None.
## @version 1
## @dg_internal
def _find_guard_hook(data: dict) -> dict | None:
    """Match on the hook ID only — never on repo URL or ordering, both of
    which differ between adopting repos (remote hook vs `repo: local`).

    @brief Find the doxygen-guard hook entry.
    @return Hook mapping or None.
    @version 1
    """
    for repo in data.get("repos") or []:
        for hook in (repo or {}).get("hooks") or []:
            if isinstance(hook, dict) and hook.get("id") == GUARD_HOOK_ID:
                return hook
    return None


## @brief The doxygen-guard release a repo pins in its pre-commit config.
## @param repo_root Repo root holding the `.pre-commit-config.yaml`.
## @return The `rev:` string of the repo declaring the doxygen-guard hook, else None.
## @version 1
## @req REQ-DDB-CONFIG-001
def pinned_guard_rev(repo_root: Path | str) -> str | None:
    """The target's OWN answer to "which doxygen-guard does this config obey".

    gh#32: a target's guard config is written against the release that repo pins,
    and parsed here by whatever release this package pins. When those disagree, the
    diagnosis an owner can act on names BOTH — and only the target's pre-commit
    config knows the first one. A `repo: local` hook pins nothing, which is itself
    the answer (None), not an error.

    @brief Read the doxygen-guard `rev:` a repo pins.
    @return The pinned rev, or None.
    @version 1
    """
    data = _load_precommit_config(Path(repo_root) / PRECOMMIT_CONFIG_NAME) or {}
    for repo in data.get("repos") or []:
        hooks = (repo or {}).get("hooks") or []
        if any(isinstance(h, dict) and h.get("id") == GUARD_HOOK_ID for h in hooks):
            rev = (repo or {}).get("rev")
            return str(rev) if rev else None
    return None


## @brief Parse a .pre-commit-config.yaml into a mapping, or None.
## @param config_path Path to the config file.
## @return The parsed mapping, or None when absent, unparseable, or not a mapping.
## @version 1
## @dg_internal
def _load_precommit_config(config_path: Path) -> dict | None:
    """Absence and malformation are the same answer to the caller — fall back
    to the Doxyfile, loudly — but only a PARSE failure is worth logging, since
    most repos simply have no such file.

    @brief Read and parse the pre-commit config.
    @return Parsed mapping or None.
    @version 1
    """
    if not config_path.is_file():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8", errors="replace"))
    except yaml.YAMLError:
        logger.error("scope: could not parse %s", config_path)
        return None
    return data if isinstance(data, dict) else None


## @brief Where a repo's doxygen-guard config is, and how that was determined.
## @version 1
@dataclass(frozen=True)
class GuardConfigLocation:
    """The discovered config path (None when there is none), the provenance of that
    answer, and every location that was tried.

    `searched` is the load-bearing field. A guard config that is not found makes
    every declaration-driven lookup fall back to a built-in default, and doing that
    without saying WHERE we looked is the silence gh#16 is about: the build succeeds,
    the index is scoped differently from what the repo declares, and nothing in the
    output distinguishes "the repo declares nothing" from "we looked in the wrong
    place".

    @brief A located (or unlocated) doxygen-guard config with its provenance.
    @version 1
    """

    path: Path | None
    source: str
    searched: tuple[str, ...] = ()

    ## @brief Human-readable list of the locations that were tried.
    ## @return Comma-joined search locations, or a note that none were tried.
    ## @version 1
    ## @req REQ-DDB-CONFIG-001
    def describe_search(self) -> str:
        """@brief Render `searched` for a log line or a fallback reason."""
        return ", ".join(self.searched) if self.searched else "no locations searched"


## @brief The guard config at the conventional repo-root location.
## @param root Resolved repo root.
## @return (path or None, description of where this looked).
## @version 1
## @dg_internal
def _guard_config_at_root(root: Path) -> tuple[Path | None, str]:
    """@brief Look for the root-level `.doxygen-guard.yaml`."""
    path = root / GUARD_CONFIG_NAME
    return (path if path.is_file() else None), str(path)


## @brief The `--config` path a pre-commit `args:` list names, if any.
## @param args The hook's `args:` value, whatever shape it has.
## @return The declared path string, or None when the flag is absent.
## @version 1
## @dg_internal
def _config_arg(args: object) -> str | None:
    """Both spellings pre-commit users write are accepted — `--config path` as two
    list items and `--config=path` as one — because a repo picking the other one is
    not a different declaration, only different punctuation.

    @brief Extract the guard config path declared in a hook's args.
    @return The path string, or None.
    @version 1
    """
    items = [str(item) for item in args] if isinstance(args, list) else []
    for index, item in enumerate(items):
        if item.startswith(f"{_CONFIG_FLAG}="):
            return item.split("=", 1)[1]
        if item == _CONFIG_FLAG and index + 1 < len(items):
            return items[index + 1]
    return None


## @brief The guard config the repo's own pre-commit hook declares via `--config`.
## @param root Resolved repo root.
## @return (path or None, description of where this looked).
## @version 1
## @dg_internal
def _guard_config_from_hook_args(root: Path) -> tuple[Path | None, str]:
    """This module ALREADY parsed `.pre-commit-config.yaml` for the hook's
    `files:`/`exclude:` and threw the rest away, so a repo that states its config
    location in the file we were already reading was ignored anyway. That is the
    whole of gh#16's "undeclared dependency on CLI arguments": the declaration was
    present and unread.

    A declared path that does not exist is reported at WARNING rather than passed on
    or silently dropped — the repo says its config is there, so its absence is a
    fact the owner wants, not a reason to fall through quietly to a guess.

    @brief Read the guard config path from the doxygen-guard hook's args.
    @return (path or None, search description).
    @version 1
    """
    config_path = root / PRECOMMIT_CONFIG_NAME
    where = f"{config_path} ({GUARD_HOOK_ID} hook {_CONFIG_FLAG} arg)"
    hook = _find_guard_hook(_load_precommit_config(config_path) or {})
    declared = _config_arg(hook.get("args")) if hook else None
    if declared is None:
        return None, where
    path = (root / declared).resolve()
    if not path.is_file():
        logger.warning(
            "guard config: %s declares %s %s, but %s does not exist",
            config_path,
            _CONFIG_FLAG,
            declared,
            path,
        )
        return None, where
    return path, where


## @brief The guard config in a conventional non-root directory, refusing to guess.
## @param root Resolved repo root.
## @return (path or None, description of where this looked).
## @version 2
## @dg_internal
def _guard_config_conventional(root: Path) -> tuple[Path | None, str]:
    """REFUSES TO GUESS among several candidates, following `discover_doxyfile`'s
    precedent and for the same reason: that function once resolved strays
    alphabetically and was caught selecting a TEST FIXTURE's Doxyfile to index a
    whole project. A wrong guard config is the same class of error — it silently
    supplies someone else's requirement-tag id pattern, catalog mapping and
    passthrough declaration — and here the fallback (built-in defaults, reported) is
    a known quantity, so guessing buys nothing.

    @brief Find a conventionally-placed guard config, or refuse on ambiguity.
    @return (path or None, search description).
    @version 2
    """
    where = ", ".join(
        str(root / directory / name)
        for directory in _GUARD_CONFIG_DIRS
        for name in _GUARD_CONFIG_NAMES
    )
    candidates = [
        candidate
        for directory in _GUARD_CONFIG_DIRS
        for name in _GUARD_CONFIG_NAMES
        if (candidate := root / directory / name).is_file()
    ]
    if len(candidates) == 1:
        return candidates[0], where
    if candidates:
        ## THE ADVICE CHANGED WITH THE CLI, and it had to. This used to end "or pass
        ## --guard-config", and that flag was deleted when the build surface collapsed to
        ## six arguments — so the sentence would have instructed a reader to pass an argument
        ## that does not exist, which is this repo's recorded worst kind of message. Both
        ## remaining actions are DECLARATIONS in the repo's own tree rather than flags, which
        ## is the direction the no-hardcoding mandate points anyway: the ambiguity is a
        ## property of the repository, so the repository is where it gets resolved.
        logger.warning(
            "guard config: found %d candidates (%s) and NOT guessing which is the "
            "repo's — name it in the %s hook's %s arg, or move it to the repo root "
            "(%s), which discovery believes without any declaration",
            len(candidates),
            ", ".join(str(path) for path in candidates),
            GUARD_HOOK_ID,
            _CONFIG_FLAG,
            GUARD_CONFIG_NAME,
        )
    return None, where


## Discovery order. Root first because an unambiguous root config needs no
## declaration to be believed; then the location the repo DECLARES in its hook args;
## then convention, which is the only step that can be ambiguous and therefore the
## only one that can refuse.
_GUARD_FINDERS = (
    (GUARD_SOURCE_ROOT, _guard_config_at_root),
    (GUARD_SOURCE_HOOK_ARGS, _guard_config_from_hook_args),
    (GUARD_SOURCE_CONVENTIONAL, _guard_config_conventional),
)


## @brief Locate a repo's doxygen-guard config: explicit, root, hook args, convention.
## @param repo_root Repo root to search.
## @param explicit An operator-supplied path that wins outright, or None.
## @return A GuardConfigLocation, whose `path` is None when nothing was found.
## @version 2
## @req REQ-DDB-CONFIG-001
def discover_guard_config(
    repo_root: Path | str, explicit: Path | str | None = None
) -> GuardConfigLocation:
    """THE single answer to "where is this repo's guard config", for every consumer.

    It used to be three independent literals — the requirement-tag id pattern and
    catalog columns read `<root>/.doxygen-guard.yaml` from `cli.py`, the
    `x-clew` passthrough read it again from `declaration.py`, and the test
    helper a third time — so `--guard-config` moved exactly one of them. A repo
    passing that flag got its id pattern from the named file and its passthrough
    declaration from the root or nowhere: two halves of one config, two files.

    Discovery (not a new flag) is deliberately the fix. The MCP server passes no
    override arguments by design, so a capability reachable only from an argument is
    not reachable from the MCP server at all — which CLAUDE.md names "a declaration
    reachable only from argv is not a declaration". Because discovery works from the
    repo root alone, a target keeping its config in `conf/` is indexable to its
    declared scope through both entry points with nothing passed.

    @brief Discover the target repo's guard config with its provenance.
    @return The located config and how it was found.
    @version 2
    """
    root = Path(repo_root).expanduser().resolve()
    if explicit is not None:
        return GuardConfigLocation(
            path=Path(explicit).expanduser().resolve(), source=GUARD_SOURCE_EXPLICIT
        )
    searched: list[str] = []
    for source, finder in _GUARD_FINDERS:
        path, where = finder(root)
        searched.append(where)
        if path is not None:
            return GuardConfigLocation(path=path, source=source, searched=tuple(searched))
    return GuardConfigLocation(path=None, source=GUARD_SOURCE_NONE, searched=tuple(searched))


## @brief Discover the guard config and log the outcome, naming where it looked.
## @param repo_root Repo root to search.
## @param explicit An operator-supplied path that wins outright, or None.
## @return The located config and how it was found.
## @version 1
## @req REQ-DDB-CONFIG-001
def discover_guard_config_logged(
    repo_root: Path | str, explicit: Path | str | None = None
) -> GuardConfigLocation:
    """Not-found is reported at WARNING and NAMES EVERY LOCATION TRIED, because the
    consequence is that the build runs on built-in defaults for the requirement-tag
    id pattern, the catalog mapping and the whole declaration passthrough. That is a
    different index from the one the repo declares, and previously the only trace of
    it was the absence of a log line.

    Absence is still not an error: most repos have their config at the root or have
    none, and a build with no declaration is a supported, useful build.

    @brief Discover the guard config, reporting the result either way.
    @return The located config.
    @version 1
    """
    location = discover_guard_config(repo_root, explicit)
    if location.path is None:
        logger.warning(
            "guard config: none found — searched %s. Falling back to built-in "
            "defaults for the requirement-tag id pattern, the requirements catalog "
            "mapping and the x-clew declaration passthrough",
            location.describe_search(),
        )
    else:
        logger.info("guard config: using %s (found via %s)", location.path, location.source)
    return location
