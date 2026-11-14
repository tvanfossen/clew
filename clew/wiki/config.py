# SPDX-License-Identifier: MIT
"""The `wiki:` section of `.clew.yaml`: what the site holds, validated by name.

1.4.0 Track 4, W5. The declaration loader accepts and drops `wiki:` (it is not a build option);
this module reads it. Every key is known by name and an unknown one is a PROBLEM, never ignored —
the same rule the build applies to its own sections, for the same reason: a misspelled key that
is silently ignored produces a site that looks complete and omits what the key asked for.

    wiki:
      title: Demo                     # site title
      docs: [README.md, "docs/**/*.md"]  # prose pages, as globs relative to the repo root
      flows:                          # sequence flows derived from the index (clew wiki flow)
        - entry: load
          qualified: Store::load      # optional identity selector
          depth: 3
          lanes: files                # files | packages | threads
          stop_at: [log]
          title: Loading
      tests:                          # CI evidence for the requirement trace (clew wiki trace)
        junit: [build/junit.xml]
        coverage: build/coverage.xml
        target_only: ["test_hw_*"]
      links:
        template: "https://host/repo/blob/{commit}/{file}#L{line}"
      audiences:
        partner:
          exclude_bodies: true
          exclude_requirement_text: true

@brief Read and validate the `wiki:` section.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

## Every key the section, a flow, the tests block and an audience may carry.
_TOP = {"title", "docs", "flows", "tests", "links", "audiences"}
_FLOW = {"entry", "qualified", "depth", "lanes", "stop_at", "title"}
_TESTS = {"junit", "coverage", "target_only"}
_LINKS = {"template"}
_AUDIENCE = {"exclude_bodies", "exclude_requirement_text"}
## Prose read when the section names none.
DEFAULT_DOCS = ("README.md", "docs/**/*.md", "docs/**/*.rst")


## @brief One flow the site derives.
## @version 1
@dataclass(frozen=True)
class FlowSpec:
    """@brief Entry, selector, depth, lanes, stop names, title. @version 1"""

    entry: str
    qualified: str | None = None
    depth: int = 3
    lanes: str = "files"
    stop_at: tuple[str, ...] = ()
    title: str = ""


## @brief One audience's redaction rules.
## @version 1
@dataclass(frozen=True)
class Audience:
    """@brief What an audience's site leaves out. @version 1"""

    exclude_bodies: bool = False
    exclude_requirement_text: bool = False


## @brief The parsed section.
## @version 1
@dataclass(frozen=True)
class WikiConfig:
    """@brief The whole `wiki:` section. @version 1"""

    title: str = "Wiki"
    docs: tuple[str, ...] = DEFAULT_DOCS
    flows: tuple[FlowSpec, ...] = ()
    junit: tuple[str, ...] = ()
    coverage: str | None = None
    target_only: tuple[str, ...] = ()
    link_template: str = ""
    audiences: dict[str, Audience] = field(default_factory=dict)


## @brief Read and validate a repository's `wiki:` section.
## @param repo_root The repository.
## @return (config, problems); problems is empty when the section is valid.
## @version 1
## @req REQ-DDB-WIKI-003
def load_wiki_config(repo_root: Path) -> tuple[WikiConfig, list[str]]:
    """A MISSING SECTION IS A VALID ONE: defaults (the README and docs/ prose, no flows) apply, so a
    repository can build a site before it has written a line of configuration.

    @brief Load the section.
    @return Config and problems.
    @version 1
    """
    import yaml

    path = Path(repo_root) / ".clew.yaml"
    raw: Any = {}
    if path.is_file():
        try:
            raw = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("wiki") or {}
        except (yaml.YAMLError, AttributeError) as exc:
            return WikiConfig(), [f".clew.yaml could not be read as YAML: {exc}"]
    if not isinstance(raw, dict):
        return WikiConfig(), ["`wiki:` must be a mapping"]
    problems = _unknown(raw, _TOP, "wiki")
    flows = tuple(_flow(f, i, problems) for i, f in enumerate(raw.get("flows") or []))
    tests = raw.get("tests") or {}
    problems += _unknown(tests, _TESTS, "wiki.tests")
    links = raw.get("links") or {}
    problems += _unknown(links, _LINKS, "wiki.links")
    audiences = {}
    for name, rules in (raw.get("audiences") or {}).items():
        problems += _unknown(rules or {}, _AUDIENCE, f"wiki.audiences.{name}")
        audiences[str(name)] = Audience(
            exclude_bodies=bool((rules or {}).get("exclude_bodies")),
            exclude_requirement_text=bool((rules or {}).get("exclude_requirement_text")),
        )
    config = WikiConfig(
        title=str(raw.get("title") or "Wiki"),
        docs=tuple(str(d) for d in raw.get("docs") or DEFAULT_DOCS),
        flows=tuple(f for f in flows if f is not None),
        junit=tuple(str(j) for j in tests.get("junit") or ()),
        coverage=str(tests["coverage"]) if tests.get("coverage") else None,
        target_only=tuple(str(t) for t in tests.get("target_only") or ()),
        link_template=str(links.get("template") or ""),
        audiences=audiences,
    )
    return config, problems


## @brief Problems for any key not in the allowed set.
## @param mapping The mapping.
## @param allowed Allowed keys.
## @param where Its dotted location, for the message.
## @return Problems.
## @version 1
## @dg_internal
def _unknown(mapping: Any, allowed: set[str], where: str) -> list[str]:
    """@brief Name unknown keys. @return Problems."""
    if not isinstance(mapping, dict):
        return [f"`{where}` must be a mapping"]
    return [
        f"`{where}.{key}` is not a known key (allowed: {', '.join(sorted(allowed))})"
        for key in mapping
        if key not in allowed
    ]


## @brief One flow entry, or None when it is unusable (a problem is recorded).
## @param raw The entry.
## @param index Its position.
## @param problems Accumulated problems; appended to.
## @return The FlowSpec or None.
## @version 1
## @dg_internal
def _flow(raw: Any, index: int, problems: list[str]) -> FlowSpec | None:
    """@brief Parse one flow. @return Spec or None."""
    where = f"wiki.flows[{index}]"
    problems += _unknown(raw, _FLOW, where)
    if not isinstance(raw, dict) or not raw.get("entry"):
        problems.append(f"`{where}` needs an `entry`")
        return None
    return FlowSpec(
        entry=str(raw["entry"]),
        qualified=str(raw["qualified"]) if raw.get("qualified") else None,
        depth=int(raw.get("depth") or 3),
        lanes=str(raw.get("lanes") or "files"),
        stop_at=tuple(str(s) for s in raw.get("stop_at") or ()),
        title=str(raw.get("title") or ""),
    )
