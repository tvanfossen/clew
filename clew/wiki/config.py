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
          animate: true               # W12: play the diagram in call order (default true)
      tests:                          # CI evidence for the requirement trace (clew wiki trace)
        junit: [build/junit.xml]
        coverage: build/coverage.xml
        target_only: ["test_hw_*"]
      links:
        template: "https://host/repo/blob/{commit}/{file}#L{line}"
        mutations: build/mutations.yaml   # W9: [{mechanism, test, killed}]
      sources:                        # W7: external node sources (JSON / TOML / YAML)
        - name: keys
          path: model/keys.toml
          items: keys                 # dotted path to a mapping (its keys are ids) or a list
          id: name                    # the id field, for a list
          doc: doc                    # the documentation field
          req: reqs                   # optional: requirement ids the node serves
      catalogs:                       # W8: sub-catalogs in sibling checkouts, read at a pin
        - name: kv
          repo: ../kv
          pin: v1.2.0
          catalog: docs/requirements.yaml
      rules:                          # W8: normative rules kept outside any repository
        - id: R1
          title: Timeouts are bounded
          status: adopted
          url: https://host/contract#R1
          requirements: [REQ-W-001]
      audiences:
        partner:
          exclude_bodies: true
          exclude_requirement_text: true

@brief Read and validate the `wiki:` section.
@version 2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

## Every key the section, a flow, the tests block and an audience may carry.
_TOP = {"title", "docs", "flows", "tests", "links", "audiences", "sources", "catalogs", "rules"}
_FLOW = {"entry", "qualified", "depth", "lanes", "stop_at", "title", "animate"}
_TESTS = {"junit", "coverage", "target_only", "mutations"}
_SOURCE = {"name", "path", "items", "id", "doc", "req"}
_CATALOG = {"name", "repo", "pin", "catalog"}
_RULE = {"id", "title", "status", "url", "requirements"}
_LINKS = {"template"}
_AUDIENCE = {"exclude_bodies", "exclude_requirement_text"}
## Prose read when the section names none.
DEFAULT_DOCS = ("README.md", "docs/**/*.md", "docs/**/*.rst")


## @brief One flow the site derives.
## v2: `animate` (W12).
## @version 2
@dataclass(frozen=True)
class FlowSpec:
    """@brief Entry, selector, depth, lanes, stop names, title, animation. @version 2"""

    entry: str
    qualified: str | None = None
    depth: int = 3
    lanes: str = "files"
    stop_at: tuple[str, ...] = ()
    title: str = ""
    animate: bool = True


## @brief One audience's redaction rules.
## @version 1
@dataclass(frozen=True)
class Audience:
    """@brief What an audience's site leaves out. @version 1"""

    exclude_bodies: bool = False
    exclude_requirement_text: bool = False


## @brief One external node source (W7).
## @version 1
@dataclass(frozen=True)
class SourceSpec:
    """@brief Name, file, items path, id / doc / requirement fields. @version 1"""

    name: str
    path: str
    items: str = ""
    id: str = ""
    doc: str = "doc"
    req: str = ""


## @brief One pinned sub-catalog (W8).
## @version 1
@dataclass(frozen=True)
class CatalogSpec:
    """@brief Name, sibling checkout, pin, catalog path inside it. @version 1"""

    name: str
    repo: str
    pin: str
    catalog: str


## @brief One external normative rule (W8).
## @version 1
@dataclass(frozen=True)
class RuleSpec:
    """@brief Rule id, title, status, url, and the requirements that realise it. @version 1"""

    id: str
    title: str = ""
    status: str = ""
    url: str = ""
    requirements: tuple[str, ...] = ()


## @brief The parsed section.
## v2: sources, catalogs, rules, mutations (W7–W9).
## @version 2
@dataclass(frozen=True)
class WikiConfig:
    """@brief The whole `wiki:` section. @version 2"""

    title: str = "Wiki"
    docs: tuple[str, ...] = DEFAULT_DOCS
    flows: tuple[FlowSpec, ...] = ()
    junit: tuple[str, ...] = ()
    coverage: str | None = None
    target_only: tuple[str, ...] = ()
    link_template: str = ""
    audiences: dict[str, Audience] = field(default_factory=dict)
    mutations: str | None = None
    sources: tuple[SourceSpec, ...] = ()
    catalogs: tuple[CatalogSpec, ...] = ()
    rules: tuple[RuleSpec, ...] = ()


## @brief Read and validate a repository's `wiki:` section.
## @param repo_root The repository.
## @param config_path A file whose `wiki:` section applies instead of `<repo>/.clew.yaml`.
## @return (config, problems); problems is empty when the section is valid.
## v2: `config_path` (document a repository without writing into it) and the W7–W9 sections.
## @version 2
## @req REQ-DDB-WIKI-003
def load_wiki_config(
    repo_root: Path, config_path: Path | None = None
) -> tuple[WikiConfig, list[str]]:
    """A MISSING SECTION IS A VALID ONE: defaults (the README and docs/ prose, no flows) apply, so a
    repository can build a site before it has written a line of configuration.

    @brief Load the section.
    @return Config and problems.
    @version 2
    """
    raw, problems = _read_section(Path(config_path or Path(repo_root) / ".clew.yaml"))
    if problems:
        return WikiConfig(), problems
    problems = _unknown(raw, _TOP, "wiki")
    flows = tuple(_flow(f, i, problems) for i, f in enumerate(raw.get("flows") or []))
    tests = raw.get("tests") or {}
    problems += _unknown(tests, _TESTS, "wiki.tests")
    links = raw.get("links") or {}
    problems += _unknown(links, _LINKS, "wiki.links")
    config = WikiConfig(
        title=str(raw.get("title") or "Wiki"),
        docs=tuple(str(d) for d in raw.get("docs") or DEFAULT_DOCS),
        flows=tuple(f for f in flows if f is not None),
        junit=tuple(str(j) for j in tests.get("junit") or ()),
        coverage=str(tests["coverage"]) if tests.get("coverage") else None,
        target_only=tuple(str(t) for t in tests.get("target_only") or ()),
        link_template=str(links.get("template") or ""),
        audiences=_audiences(raw.get("audiences") or {}, problems),
        mutations=str(tests["mutations"]) if tests.get("mutations") else None,
        sources=_entries(raw, "sources", _SOURCE, ("name", "path"), _source, problems),
        catalogs=_entries(raw, "catalogs", _CATALOG, tuple(sorted(_CATALOG)), _catalog, problems),
        rules=_entries(raw, "rules", _RULE, ("id",), _rule, problems),
    )
    return config, problems


## @brief The raw `wiki:` mapping of a config file.
## @param path The file; absent means an empty section.
## @return (section, problems).
## @version 1
## @dg_internal
def _read_section(path: Path) -> tuple[dict[str, Any], list[str]]:
    """@brief Read YAML. @return Section and problems."""
    import yaml

    raw: Any = {}
    if path.is_file():
        try:
            raw = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("wiki") or {}
        except (yaml.YAMLError, AttributeError) as exc:
            return {}, [f"{path.name} could not be read as YAML: {exc}"]
    if not isinstance(raw, dict):
        return {}, ["`wiki:` must be a mapping"]
    return raw, []


## @brief Every audience's rules.
## @param raw The `audiences` mapping.
## @param problems Accumulated problems; appended to.
## @return {name: Audience}.
## @version 1
## @dg_internal
def _audiences(raw: Any, problems: list[str]) -> dict[str, Audience]:
    """@brief Parse audiences. @return Rules by name."""
    out = {}
    for name, rules in (raw if isinstance(raw, dict) else {}).items():
        problems += _unknown(rules or {}, _AUDIENCE, f"wiki.audiences.{name}")
        out[str(name)] = Audience(
            exclude_bodies=bool((rules or {}).get("exclude_bodies")),
            exclude_requirement_text=bool((rules or {}).get("exclude_requirement_text")),
        )
    return out


## @brief One list section parsed entry by entry; an entry missing a required key is dropped.
## @param raw The whole section.
## @param key The list's key.
## @param allowed Keys an entry may carry.
## @param required Keys an entry must carry.
## @param make Builds the spec from a validated entry.
## @param problems Accumulated problems; appended to.
## @return The specs.
## @version 1
## @dg_internal
def _entries(
    raw: dict[str, Any],
    key: str,
    allowed: set[str],
    required: tuple[str, ...],
    make: Any,
    problems: list[str],
) -> tuple[Any, ...]:
    """@brief Parse a list section. @return Specs."""
    out = []
    for i, entry in enumerate(raw.get(key) or []):
        where = f"wiki.{key}[{i}]"
        problems += _unknown(entry, allowed, where)
        missing = [k for k in required if not isinstance(entry, dict) or entry.get(k) in (None, "")]
        if missing:
            problems.append(f"`{where}` needs {', '.join(f'`{m}`' for m in missing)}")
            continue
        out.append(make(entry))
    return tuple(out)


## @brief A SourceSpec from a validated entry.
## @param e The entry.
## @return The spec.
## @version 1
## @dg_internal
def _source(e: dict[str, Any]) -> SourceSpec:
    """@brief Build. @return Spec."""
    return SourceSpec(
        name=str(e["name"]),
        path=str(e["path"]),
        items=str(e.get("items") or ""),
        id=str(e.get("id") or ""),
        doc=str(e.get("doc") or "doc"),
        req=str(e.get("req") or ""),
    )


## @brief A CatalogSpec from a validated entry.
## @param e The entry.
## @return The spec.
## @version 1
## @dg_internal
def _catalog(e: dict[str, Any]) -> CatalogSpec:
    """@brief Build. @return Spec."""
    return CatalogSpec(
        name=str(e["name"]), repo=str(e["repo"]), pin=str(e["pin"]), catalog=str(e["catalog"])
    )


## @brief A RuleSpec from a validated entry.
## @param e The entry.
## @return The spec.
## @version 1
## @dg_internal
def _rule(e: dict[str, Any]) -> RuleSpec:
    """@brief Build. @return Spec."""
    return RuleSpec(
        id=str(e["id"]),
        title=str(e.get("title") or ""),
        status=str(e.get("status") or ""),
        url=str(e.get("url") or ""),
        requirements=tuple(str(r) for r in e.get("requirements") or ()),
    )


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
## v2: `animate`.
## @version 2
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
        animate=bool(raw.get("animate", True)),
    )
