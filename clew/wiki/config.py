# SPDX-License-Identifier: MIT
"""The `wiki:` section of `.clew.yaml`: what the site holds, validated by name.

1.4.0 Track 4, W5. The declaration loader accepts and drops `wiki:` (it is not a build option);
this module reads it. Every key is known by name and an unknown one is a PROBLEM, never ignored —
the same rule the build applies to its own sections, for the same reason: a misspelled key that
is silently ignored produces a site that looks complete and omits what the key asked for.

ONE REFERENCE (R5-CFG F17, 2.0.0): every key, with an example, is in docs/WIKI.md, and
`tests/test_docs_current.py` checks that block names every key this module accepts. This docstring
used to carry a second copy, and the two disagreed.

@brief Read and validate the `wiki:` section.
@version 4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..declaration import TESTS_KEYS, TESTS_PATHS

## Every key the section, a flow, the tests block and an audience may carry.
_TOP = {
    "title",
    "docs",
    "flows",
    "links",
    "audiences",
    "sources",
    "rules",
    "theme",
    "roadmap",
    "entry_point_depth",
    "components",
    "issues",
    "tooling",
    "adrs",
    "doc_kinds",
    ## R5-CFG C1-C5, C7, C8, W6 (2.0.0): the numbers the build used to assume.
    "measured_depth",
    "measured_steps",
    "path_depth",
    "trace_depth",
    "trace_timeout",
    "trace_python",
    "component_depth",
    "web",
    ## S9 (2.0.0): `check: {ears: true}`, the opt-in EARS badge (never a gate).
    "check",
    ## #70 (2.0.0, P5.8): `sbom: {files: [...], accepted: [...]}` — the SBOM page's inputs.
    "sbom",
    ## 2.0.0 (owner Q/A 2026-11-20): which tests get a page — `linked` (default) | `all` | `none`.
    "test_pages",
    ## PAPI (2.0.0, owner Q/A 2026-11-19): the public-header globs the API reference is drawn from.
    "api",
    ## V6 (2.0.0, owner Q/A 2026-11-20): how many lines of a body a symbol page bundles.
    "body_lines",
    "test_slices",
}
## Each tuning key's former constant — the default when it is not declared.
TUNING_DEFAULTS = {
    "measured_depth": 12,
    "measured_steps": 400,
    "path_depth": 12,
    "trace_depth": 2,
    "trace_timeout": 600,
    "component_depth": 2,
}
_WEB = {"max_ring"}
## The per-test report cap, in MiB (`tests.max_report_mb`).
DEFAULT_MAX_REPORT_MB = 64
_THEME = {"name", "palette", "css", "logo", "fonts"}
## The palette tokens of the default theme, as a reader writes them, and the CSS custom property
## each one sets. R5-CFG F25 (2.0.0): the config used to expose the stylesheet's abbreviations
## (`acc`, `accbg`, `rule2`), which were about to become semver-covered; the words are the
## contract and the CSS names stay internal, so the stylesheet did not change.
PALETTE = {
    "surface": "surface",
    "paper": "paper",
    "muted": "muted",
    "inset": "inset",
    "ink": "ink",
    "ink_soft": "ink2",
    "faint": "faint",
    "rule": "rule",
    "rule_strong": "rule2",
    "accent": "acc",
    "accent_bg": "accbg",
    "accent_ink": "accink",
    "root": "root",
    "root_bg": "rootbg",
    "error": "err",
    "error_bg": "errbg",
    "warning": "warn",
    "warning_bg": "warnbg",
}
THEME_TOKENS = tuple(PALETTE)
## An old abbreviation, refused with the word that replaced it.
_PALETTE_RENAMED = {css: word for word, css in PALETTE.items() if css != word}
## Keys renamed in 2.0.0, refused with a pointer rather than as unknown — "unknown" would send a
## reader hunting a typo in a key that was correct until this release.
_RENAMED = {"entry_points": "entry_point_depth"}
## Keys that MOVED to the top-level `requirements:` section in 2.0.0 (R5-CFG F6/F7): the catalog
## is the repository's, read by the index, the gate and the wiki from one place.
_MOVED = {
    "catalogs": "`requirements.external` (entries {repo, rev, path, name})",
    "needs": "`requirements.needs`",
    "impact": "the gate's report directory (`guard.impact.report_dir`), which the wiki now reads",
    "tests": "the top-level `tests:` section (where tests live and the evidence their runs leave)",
}
_FLOW = {
    "entry",
    "qualified",
    "depth",
    "lanes",
    "stop_at",
    "title",
    "animate",
    "file",
    "role",
    "measured_depth",
    "max_steps",
    ## W-1/W-5 (owner review 2026-11-22): declared, never derived.
    "intent",
    "scenario",
    "example",
}
## The words a Gherkin step line begins with.
GHERKIN_KEYWORDS = ("Given", "When", "Then", "And", "But")
## The roles a flow is grouped under on the Flows page (round 3, P1e).
FLOW_ROLES = ("product", "threads", "tooling", "tests")
## The kinds a document is grouped under (Diátaxis, plus agent-facing docs kept apart).
DOC_KINDS = ("tutorial", "howto", "reference", "explanation", "agents")
## Where architecture decision records are looked for, unless `wiki.adrs` says otherwise.
DEFAULT_ADRS = ("docs/adr/*.md", "doc/adr/*.md", "docs/decisions/*.md", "adr/*.md")
## Paths whose entry points are tooling, unless `wiki.tooling` says otherwise.
## D2 (2.0.0): `acceptance/*` was this repository's own layout; it declares it for itself.
DEFAULT_TOOLING = ("scripts/*", "tools/*", "benchmarks/*", "examples/*")
## The evidence keys of the top-level `tests:` section (2.0.0, R5-CFG F20) — the declaration's own
## set, so the index and the wiki accept exactly the same keys; `paths` is the index's.
_TESTS = set(TESTS_KEYS - {TESTS_PATHS})
_RESULT = {"format", "path"}
_SOURCE = {"name", "path", "items", "id", "doc", "req"}
_RULE = {"id", "title", "status", "url", "requirements"}
_LINKS = {"template"}
_AUDIENCE = {"exclude_bodies", "exclude_requirement_text", "exclude_owners"}
## Prose read when the section names none.
DEFAULT_DOCS = ("README.md", "docs/**/*.md", "docs/**/*.rst")


## @brief One flow the site derives.
## v2: `animate` (W12).
## v3: `file` — the entry's file, when its name is shared (every `def main`).
## v4 (2.0.0): measured_depth, max_steps per flow (R5-CFG C1/C2).
## @version 4
@dataclass(frozen=True)
class FlowSpec:
    """@brief Entry, selector, file, depth, lanes, stop names, title, animation, role. @version 5"""

    entry: str
    qualified: str | None = None
    depth: int = 3
    ## 2.0.0 (P5.6, owner round 5): block lanes by default (was `files`).
    lanes: str = "blocks"
    stop_at: tuple[str, ...] = ()
    title: str = ""
    animate: bool = True
    file: str | None = None
    ## `product`, `threads` or `tooling`; "" = classified by the build (tooling paths, else product).
    role: str = ""
    ## R5-CFG C1/C2 (2.0.0): this flow's measured expansion depth and step cap; None inherits
    ## `wiki.measured_depth` / `wiki.measured_steps`.
    measured_depth: int | None = None
    max_steps: int | None = None
    ## W-1/W-5 (owner review 2026-11-22, declared only): one plain sentence of what the flow is for,
    ## its Gherkin scenario (one step per line), and a worked example (input, output).
    intent: str = ""
    scenario: tuple[str, ...] = ()
    example: tuple[str, str] | None = None


## @brief The W15/W16 evidence imports of the top-level `tests:`, as declared (paths relative to the repo).
## v2: `evidence_fields` — catalog fields whose test files link their tests; `infer_depth`
## (call-graph inference) and `contexts` (per-test coverage) — tests need no tag.
## v3: `traces` — OTLP JSON traces of test runs, drawn over their test flows (round 3, P4b).
## @version 3
@dataclass(frozen=True)
class EvidenceInputs:
    """@brief Reports, gcov, mapping, features, layers, catalog, inference, traces. @version 3"""

    results: tuple[tuple[str, str], ...] = ()
    gcov: tuple[str, ...] = ()
    mapping: str | None = None
    features: tuple[str, ...] = ()
    layers: tuple[tuple[str, tuple[str, ...]], ...] | None = None
    min_layers: int | None = None
    evidence_fields: tuple[str, ...] = ("x-evidence", "evidence")
    infer_depth: int | None = None
    contexts: str | None = None
    traces: tuple[str, ...] = ()


## @brief The site's theme (W13).
## @version 1
@dataclass(frozen=True)
class ThemeSpec:
    """@brief Sphinx theme name, palette overrides, extra CSS, logo, bundled fonts. @version 1"""

    name: str = "clew"
    palette: tuple[tuple[str, str], ...] = ()
    css: tuple[str, ...] = ()
    logo: str | None = None
    fonts: bool = True


## @brief One audience's redaction rules.
## @version 1
@dataclass(frozen=True)
class Audience:
    """@brief What an audience's site leaves out. @version 1"""

    exclude_bodies: bool = False
    exclude_requirement_text: bool = False
    ## P5 (2.0.0): who owns what (CODEOWNERS / MAINTAINERS) left off the map and the file pages.
    exclude_owners: bool = False


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
## v3: evidence imports (W15/W16).
## v4: theme (W13) and roadmap (W17).
## v5: impact report path.
## v6: entry_points (auto-derived entry-point flows, their depth).
## v7: components (the map's declared groupings).
## v8: issues (the tracker prefilled issue links open).
## v9: tooling (paths whose entry points group under Tooling).
## v10: test_flows (how many directly linked tests are drawn as flows).
## v11: issues_fetch.
## v12: needs (a Sphinx-needs import).
## v13: adrs, doc_kinds.
## v14 (round 5): test_flows removed — tests are slices of the master flows.
## v15 (2.0.0): `needs` comes from `requirements.needs`; the orphan test_flows comment is gone.
## v16 (2.0.0): the tuning keys (R5-CFG C1-C5, C7-C9, W6).
## v17 (2.0.0): `docs_declared`.
## @version 17
@dataclass(frozen=True)
class WikiConfig:
    """@brief The whole `wiki:` section. @version 5"""

    title: str = "Wiki"
    docs: tuple[str, ...] = DEFAULT_DOCS
    ## 2.0.0 (consumer finding): whether `wiki.docs` was declared. `clew wiki check` reports a
    ## declared glob that matches nothing; a built-in default that matches nothing is no fault.
    docs_declared: bool = False
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
    inputs: EvidenceInputs = EvidenceInputs()
    theme: ThemeSpec = ThemeSpec()
    roadmap: str | None = None
    impact: str | None = None
    entry_point_depth: int = 2
    components: tuple[tuple[str, tuple[str, ...]], ...] = ()
    ## (provider, project) declared; None = read the origin remote.
    issues: tuple[str, str] | None = None
    ## False when `issues: false` — no issue links at all.
    issues_enabled: bool = True
    ## True when `issues.fetch` asks the build to read open issues (the build's only network use).
    issues_fetch: bool = False
    ## S9 (2.0.0): `check.ears` — the EARS badge on requirement pages and notes from `check`.
    ears: bool = False
    ## #70 (2.0.0): SBOM files to render (repo-relative globs) and the accepted-licence list.
    sbom_files: tuple[str, ...] = ("sbom.spdx.json", "bom.cdx.json")
    sbom_accepted: tuple[str, ...] = ()
    ## Owner Q/A 2026-11-20: `linked` — tests the requirement evidence names, implicit links
    ## included (today's set); `all` — every test the index recognises; `none` — no per-test page.
    test_pages: str = "linked"
    ## PAPI: public-header globs; () = no API tab (off unless declared).
    api: tuple[str, ...] = ()
    ## V6: lines of a body bundled on its symbol page; past it, a link to the full source.
    body_lines: int = 120
    ## OWNER Q/A 2026-11-20 (after P6): slices drawn on a test page; the rest are links.
    test_slices: int = 1
    ## Entropic's gap 1: the repository's declared doc tags (`guard.validate.extra_tags`), shown as
    ## labelled fields on API pages. Read raw: the gate's own loader refuses doxygen-guard
    ## leftovers, and a wiki build must not fail on the gate's account.
    doc_tags: tuple[str, ...] = ()
    ## Path globs whose entry points are tooling flows.
    tooling: tuple[str, ...] = DEFAULT_TOOLING
    ## R5-CFG C1-C5, C7-C9, W6 (2.0.0): the build's numbers, declared (see TUNING_DEFAULTS).
    measured_depth: int = 12
    measured_steps: int = 400
    path_depth: int = 12
    trace_depth: int = 2
    trace_timeout: int = 600
    trace_python: str | None = None
    component_depth: int = 2
    web_max_ring: int = 8
    max_report_mb: int = DEFAULT_MAX_REPORT_MB
    ## A Sphinx-needs `needs.json` contributing requirements (from `requirements.needs`), or None.
    needs: str | None = None
    ## Globs of architecture decision records.
    adrs: tuple[str, ...] = DEFAULT_ADRS
    ## (glob, kind) pairs: which document is a tutorial, how-to, reference, explanation or agents.
    doc_kinds: tuple[tuple[str, str], ...] = ()


## @brief Read and validate a repository's `wiki:` section.
## @param repo_root The repository.
## @param config_path A file whose `wiki:` section applies instead of `<repo>/.clew.yaml`.
## @return (config, problems); problems is empty when the section is valid.
## v2: `config_path` (document a repository without writing into it) and the W7–W9 sections.
## v3: the W15/W16 evidence imports.
## v4: theme and roadmap.
## v5: impact.
## v6: entry_points.
## v7: components.
## v8: issues.
## v9: tooling.
## v10: test_flows.
## v11: issues.fetch.
## v12: needs.
## v13: adrs, doc_kinds.
## v14 (round 5): test_flows removed.
## v15 (2.0.0, R5-CFG): list keys through `_strings` (one string is one entry, [] is empty, any other
## type is a problem); `entry_points` renamed `entry_point_depth`, the old key refused with a pointer.
## v16 (2.0.0, R5-CFG F6/F7/F9): catalogs and needs come from the top-level `requirements:`;
## `wiki.catalogs`, `wiki.needs` and `wiki.impact` are refused with where they went.
## v17: tests come from the top-level tests: section; wiki.tests is refused (2.0.0, R5-CFG F20)
## v18: reads the tuning keys (2.0.0, R5-CFG C1-C9)
## v19: records docs_declared (2.0.0)
## v20: EARS badge and check notes (2.0.0, S9)
## v21: wiki.sbom (2.0.0, P5.8)
## v22: wiki.test_pages (tests category (2.0.0, owner Q/A 2026-11-20))
## v23: wiki.api (public-API reference (2.0.0, PAPI))
## v24: viewer caps V3/V5/V6 (2.0.0, owner Q/A 2026-11-20)
## v25: doc_tags (entropic's PAPI gaps 1-3 (2.0.0))
## v26: wiki.test_slices (slice cap (owner Q/A 2026-11-20, after P6))
## @version 26
## @req REQ-DDB-WIKI-003
def load_wiki_config(
    repo_root: Path, config_path: Path | None = None
) -> tuple[WikiConfig, list[str]]:
    """A MISSING SECTION IS A VALID ONE: defaults (the README and docs/ prose, no flows) apply, so a
    repository can build a site before it has written a line of configuration.

    @brief Load the section.
    @return Config and problems.
    @version 15
    """
    raw, problems = _read_section(Path(config_path or Path(repo_root) / ".clew.yaml"))
    if problems:
        return WikiConfig(), problems
    problems = _renamed(raw, "wiki") + _unknown(
        {k: v for k, v in raw.items() if k not in _RENAMED and k not in _MOVED}, _TOP, "wiki"
    )
    requirements = _requirements_section(
        Path(config_path or Path(repo_root) / ".clew.yaml"), problems
    )
    flows = tuple(_flow(f, i, problems) for i, f in enumerate(raw.get("flows") or []))
    tests = _top_level(Path(config_path or Path(repo_root) / ".clew.yaml"), "tests")
    problems += _unknown(tests, set(TESTS_KEYS), "tests")
    links = raw.get("links") or {}
    problems += _unknown(links, _LINKS, "wiki.links")
    config = WikiConfig(
        title=str(raw.get("title") or "Wiki"),
        docs=_strings(raw, "docs", DEFAULT_DOCS, "wiki", problems),
        docs_declared="docs" in raw,
        flows=tuple(f for f in flows if f is not None),
        junit=_strings(tests, "junit", (), "tests", problems),
        coverage=str(tests["coverage"]) if tests.get("coverage") else None,
        target_only=_strings(tests, "target_only", (), "tests", problems),
        link_template=str(links.get("template") or ""),
        audiences=_audiences(raw.get("audiences") or {}, problems),
        mutations=str(tests["mutations"]) if tests.get("mutations") else None,
        sources=_entries(raw, "sources", _SOURCE, ("name", "path"), _source, problems),
        catalogs=_pinned_catalogs(requirements),
        rules=_entries(raw, "rules", _RULE, ("id",), _rule, problems),
        inputs=_inputs(tests, problems),
        theme=_theme(raw.get("theme") or {}, problems),
        roadmap=str(raw["roadmap"]) if raw.get("roadmap") else None,
        impact=_declared_report(Path(config_path or Path(repo_root) / ".clew.yaml")),
        entry_point_depth=int(raw.get("entry_point_depth", 2)),
        components=_components(raw.get("components") or {}, problems),
        issues=_issues(raw.get("issues"), problems),
        issues_enabled=raw.get("issues") is not False,
        issues_fetch=isinstance(raw.get("issues"), dict) and bool(raw["issues"].get("fetch")),
        ears=_ears(raw.get("check"), problems),
        **_sbom(raw.get("sbom"), problems),
        test_pages=_one_of(raw, "test_pages", TEST_PAGES, problems),
        api=_strings(raw, "api", (), "wiki", problems),
        body_lines=_positive(raw, "body_lines", 120, problems),
        test_slices=_positive(raw, "test_slices", 1, problems),
        doc_tags=_doc_tags(Path(config_path or Path(repo_root) / ".clew.yaml")),
        tooling=_strings(raw, "tooling", DEFAULT_TOOLING, "wiki", problems),
        needs=str(requirements["needs"]) if requirements.get("needs") else None,
        adrs=_strings(raw, "adrs", DEFAULT_ADRS, "wiki", problems),
        doc_kinds=_doc_kinds(raw.get("doc_kinds") or {}, problems),
        **_tuning(raw, tests, problems),
    )
    return config, problems


## @brief The declared component groupings, in the order written.
## @param raw The `components` mapping.
## @param problems Appended to.
## @return (name, globs) pairs.
## @version 1
## @utility
def _components(raw: Any, problems: list[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """@brief Parse groupings. @return Pairs."""
    if not isinstance(raw, dict):
        problems.append("`wiki.components` must map a component name to a list of path globs")
        return ()
    out = []
    for name, globs in raw.items():
        if not isinstance(globs, list) or not all(isinstance(g, str) for g in globs):
            problems.append(f"`wiki.components.{name}` must be a list of path globs")
            continue
        out.append((str(name), tuple(globs)))
    return tuple(out)


## @brief The raw `wiki:` mapping of a config file.
## @param path The file; absent means an empty section.
## @return (section, problems).
## @version 1
## @utility
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
## v2: exclude_owners (2.0.0, P5)
## @version 2
## @utility
def _audiences(raw: Any, problems: list[str]) -> dict[str, Audience]:
    """@brief Parse audiences. @return Rules by name."""
    out = {}
    for name, rules in (raw if isinstance(raw, dict) else {}).items():
        problems += _unknown(rules or {}, _AUDIENCE, f"wiki.audiences.{name}")
        out[str(name)] = Audience(
            exclude_bodies=bool((rules or {}).get("exclude_bodies")),
            exclude_requirement_text=bool((rules or {}).get("exclude_requirement_text")),
            exclude_owners=bool((rules or {}).get("exclude_owners")),
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
## @utility
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
## @utility
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


## @brief The top-level `requirements:` section of the same file, read by the gate's reader.
## @param path The `.clew.yaml`.
## @param problems Appended to when the section is invalid.
## @return The section, or {} when undeclared or invalid.
## @version 1
## @utility
def _requirements_section(path: Path, problems: list[str]) -> dict[str, Any]:
    """THE GATE'S OWN READER, so the wiki can never accept a catalog section the gate refuses.

    @brief Read `requirements:`.
    @return Section or {}.
    """
    from ..guard.config import read_requirements_section
    from ..guard.errors import ConfigError

    if not path.is_file():
        return {}
    try:
        return read_requirements_section(path) or {}
    except ConfigError as exc:
        problems.extend(f"`requirements`: {p}" for p in (exc.problems or [exc.message]))
        return {}


## @brief A top-level section of the same file, as a mapping.
## @param path The config file.
## @param key The section.
## @return The section, or {} when absent (a non-mapping is left to the declaration loader).
## @version 1
## @utility
def _top_level(path: Path, key: str) -> dict[str, Any]:
    """@brief Read one top-level section. @return Mapping."""
    import yaml

    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    value = doc.get(key) if isinstance(doc, dict) else None
    return value if isinstance(value, dict) else {}


## @brief The impact report the gate section of the SAME file declares, when it declares one.
## @param path The config file the wiki was given.
## @return `<guard.impact.report_dir>/impact.json`, or None to use the repository's own gate config.
## @version 1
## @utility
def _declared_report(path: Path) -> str | None:
    """AN OUT-OF-TREE CONFIG (`clew wiki build --config FILE`) carries its own `guard:` section, so
    the report directory is read from that file rather than from the repository's (R5-CFG F9).

    @brief Read `guard.impact.report_dir` from this file.
    @return Path string or None.
    """
    from ..guard.config import REPORT_JSON, read_guard_section
    from ..guard.errors import ConfigError

    if not path.is_file():
        return None
    try:
        guard = read_guard_section(path) or {}
    except ConfigError:
        return None
    declared = (guard.get("impact") or {}).get("report_dir") if isinstance(guard, dict) else None
    return str(Path(str(declared)) / REPORT_JSON) if declared else None


## @brief The wiki's sub-catalogues: every PINNED `requirements.external` entry.
## @param requirements The top-level section.
## @return Specs, in the order written.
## @version 1
## @utility
def _pinned_catalogs(requirements: dict[str, Any]) -> tuple[CatalogSpec, ...]:
    """ONE SHAPE (R5-CFG F6): `{repo, rev, path, name?}` replaced `wiki.catalogs`'
    `{name, repo, pin, catalog}`. A path-only entry is this repository's own file and adds no
    sub-catalogue; a missing `name` is the checkout's directory name.

    @brief Pinned catalogues.
    @return Specs.
    """
    return tuple(
        CatalogSpec(
            name=str(e.get("name") or Path(str(e["repo"])).name),
            repo=str(e["repo"]),
            pin=str(e["rev"]),
            catalog=str(e["path"]),
        )
        for e in requirements.get("external") or []
        if isinstance(e, dict) and {"repo", "rev", "path"} <= set(e)
    )


## @brief A RuleSpec from a validated entry.
## @param e The entry.
## @return The spec.
## @version 1
## @utility
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
## @utility
def _unknown(mapping: Any, allowed: set[str], where: str) -> list[str]:
    """@brief Name unknown keys. @return Problems."""
    if not isinstance(mapping, dict):
        return [f"`{where}` must be a mapping"]
    return [
        f"`{where}.{key}` is not a known key (allowed: {', '.join(sorted(allowed))})"
        for key in mapping
        if key not in allowed
    ]


## @brief Problems for keys renamed in 2.0.0, each naming its replacement.
## @param mapping The section.
## @param where Its dotted location.
## @return Problems.
## v2: also names keys that moved to requirements: / report_dir (2.0.0)
## @version 2
## @utility
def _renamed(mapping: Any, where: str) -> list[str]:
    """@brief Point a renamed or moved key at its new home. @return Problems."""
    if not isinstance(mapping, dict):
        return []
    return [
        f"`{where}.{old}` was renamed `{new}` in 2.0.0 — it holds a depth, not a list of entry points"
        for old, new in _RENAMED.items()
        if old in mapping
    ] + [
        f"`{where}.{old}` moved in 2.0.0 to {new}" for old, new in _MOVED.items() if old in mapping
    ]


## @brief A list-of-strings key, read as written.
## @param mapping The section holding the key.
## @param key The key.
## @param default Used ONLY when the key is absent.
## @param where The section's dotted location, for the problem text.
## @param problems Appended to.
## @return The strings.
## @version 1
## @utility
def _strings(
    mapping: dict[str, Any], key: str, default: tuple[str, ...], where: str, problems: list[str]
) -> tuple[str, ...]:
    """ONE RULE FOR EVERY LIST KEY (R5-CFG F5 / W9). Absent takes the default; `[]` (or null) is
    an explicit "none"; one string is a one-item list, the precedent `gcov` and `theme.css` set;
    anything else is a problem. Before, nine list keys iterated a string into its characters and
    `docs: []` silently became the default docs.

    @brief Read a string-list key.
    @return Strings.
    """
    if key not in mapping:
        return tuple(default)
    value = mapping[key]
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value):
        return tuple(str(v) for v in value)
    problems.append(f"`{where}.{key}` must be a list of strings (or one string)")
    return tuple(default)


## @brief One flow entry, or None when it is unusable (a problem is recorded).
## @param raw The entry.
## @param index Its position.
## @param problems Accumulated problems; appended to.
## @return The FlowSpec or None.
## v2: `animate`.
## v3: `file`.
## v4: `role` (one of FLOW_ROLES).
## v5 (2.0.0): `depth: 0` is a problem, not 3; `stop_at` through `_strings`.
## v6: measured_depth and max_steps per flow (2.0.0, R5-CFG C1/C2)
## v7: block lanes by default (2.0.0, P5.6)
## v8: intent, scenario, example (W-1, W-5)
## @version 8
## @utility
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
        depth=_depth(raw, where, problems),
        lanes=str(raw.get("lanes") or "blocks"),
        stop_at=_strings(raw, "stop_at", (), where, problems),
        title=str(raw.get("title") or ""),
        animate=bool(raw.get("animate", True)),
        file=str(raw["file"]) if raw.get("file") else None,
        role=_role(raw.get("role"), where, problems),
        measured_depth=_count(raw, "measured_depth", 0, where, problems)
        if "measured_depth" in raw
        else None,
        max_steps=_count(raw, "max_steps", 0, where, problems) if "max_steps" in raw else None,
        intent=" ".join(str(raw.get("intent") or "").split()),
        scenario=_scenario(raw.get("scenario"), where, problems),
        example=_example(raw.get("example"), where, problems),
    )


## @brief A flow's declared scenario, one Gherkin step per line.
## @param value A block string or a list of lines.
## @param where The flow's location.
## @param problems Appended to.
## @return The lines.
## @version 1
## @utility
def _scenario(value: Any, where: str, problems: list[str]) -> tuple[str, ...]:
    """W-1: each line starts with a Gherkin keyword; any other line is named, never dropped.

    @brief Read a scenario.
    @return Lines.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list):
        problems.append(f"`{where}.scenario` must be text or a list of lines")
        return ()
    lines = tuple(" ".join(str(x).split()) for x in value if str(x).strip())
    for line in lines:
        if line.split(" ", 1)[0] not in GHERKIN_KEYWORDS:
            problems.append(
                f"`{where}.scenario` line {line!r} must start with one of "
                + ", ".join(GHERKIN_KEYWORDS)
            )
    return lines


## @brief A flow's declared worked example.
## @param value `{input, output}`.
## @param where The flow's location.
## @param problems Appended to.
## @return (input, output), or None.
## @version 1
## @utility
def _example(value: Any, where: str, problems: list[str]) -> tuple[str, str] | None:
    """W-5: both halves are the repository's own words, shown as written.

    @brief Read an example.
    @return Pair or None.
    """
    if value is None:
        return None
    problems += _unknown(value, {"input", "output"}, f"{where}.example")
    if not isinstance(value, dict) or not value.get("input") or not value.get("output"):
        problems.append(f"`{where}.example` needs `input` and `output`")
        return None
    return str(value["input"]).strip(), str(value["output"]).rstrip()


## @brief The tuning keys, each read as a whole number of at least 1.
## @param raw The `wiki:` section.
## @param tests The top-level `tests:` section.
## @param problems Appended to.
## @return WikiConfig keyword arguments.
## @version 1
## @utility
def _tuning(raw: dict[str, Any], tests: dict[str, Any], problems: list[str]) -> dict[str, Any]:
    """ONE RULE (R5-CFG, 2.0.0): absent is the former constant; anything but an integer of at least
    1 is a problem and the default stands — never a silent 0 that would draw nothing.

    @brief Read tuning keys.
    @return Keyword arguments.
    """
    out = {k: _count(raw, k, d, "wiki", problems) for k, d in TUNING_DEFAULTS.items()}
    web = raw.get("web") or {}
    problems += _unknown(web, _WEB, "wiki.web")
    out["web_max_ring"] = _count(
        web if isinstance(web, dict) else {}, "max_ring", 8, "wiki.web", problems
    )
    out["max_report_mb"] = _count(tests, "max_report_mb", DEFAULT_MAX_REPORT_MB, "tests", problems)
    python = raw.get("trace_python")
    out["trace_python"] = str(python) if python else None
    return out


## @brief A whole number of at least 1, or the default with a problem.
## @param mapping The section.
## @param key The key.
## @param default Its default.
## @param where The section's location.
## @param problems Appended to.
## @return The value.
## @version 1
## @utility
def _count(mapping: dict[str, Any], key: str, default: int, where: str, problems: list[str]) -> int:
    """@brief Read one count. @return Count."""
    value = mapping.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        problems.append(f"`{where}.{key}` must be a whole number of at least 1")
        return default
    return value


## @brief A flow's declared depth: omitted is 3, anything below 1 is a problem.
## @param raw The flow entry.
## @param where Its location.
## @param problems Appended to.
## @return The depth.
## @version 1
## @utility
def _depth(raw: dict[str, Any], where: str, problems: list[str]) -> int:
    """R5-CFG F16: `depth: 0` used to read 3 (`int(raw.get("depth") or 3)`). A depth of 0 draws
    nothing, so it is reported; the flow keeps the default rather than being dropped.

    @brief Read a flow depth.
    @return Depth.
    """
    value = raw.get("depth", 3)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        problems.append(f"`{where}.depth` must be a whole number of hops, at least 1")
        return 3
    return value


## @brief A flow's declared role, checked.
## @param raw The value, or None.
## @param where The flow's location, for the problem text.
## @param problems Appended to.
## @return The role, or "" when undeclared or unknown.
## @version 1
## @utility
def _role(raw: Any, where: str, problems: list[str]) -> str:
    """@brief Parse a role. @return Role."""
    if raw is None:
        return ""
    if raw not in FLOW_ROLES:
        problems.append(f"`{where}.role` must be one of {', '.join(FLOW_ROLES)}")
        return ""
    return str(raw)


## @brief The evidence imports of a `tests` block.
## @param tests The block.
## @param problems Accumulated problems; appended to.
## @return The inputs.
## v2: evidence_fields.
## v3: traces.
## v4 (round 4): an omitted `infer_depth` is the full transitive closure (None), not 2 hops.
## v5 (2.0.0): list keys through `_strings`; `min_layers: 0` is 0, not "off".
## v6: names the top-level tests: section (2.0.0, R5-CFG F20)
## @version 6
## @utility
def _inputs(tests: dict[str, Any], problems: list[str]) -> EvidenceInputs:
    """A RESULT FORMAT IS DECLARED, so an entry without one is a problem, never a sniffed guess.

    @brief Parse imports.
    @return Inputs.
    @version 5
    """
    from .imports import RESULT_FORMATS

    results = _entries(tests, "results", _RESULT, ("format", "path"), _result, problems)
    problems += [
        f"`tests.results`: format {fmt!r} is not known ({', '.join(RESULT_FORMATS)})"
        for fmt, _path in results
        if fmt not in RESULT_FORMATS
    ]
    layers = tests.get("layers")
    if layers is not None and not isinstance(layers, dict):
        problems.append("`tests.layers` must map a layer name to path globs")
        layers = None
    gcov = tests.get("gcov") or ()
    return EvidenceInputs(
        results=results,
        gcov=(str(gcov),) if isinstance(gcov, str) else tuple(str(g) for g in gcov),
        mapping=str(tests["mapping"]) if tests.get("mapping") else None,
        features=_strings(tests, "features", (), "tests", problems),
        layers=None
        if layers is None
        else tuple((str(k), tuple(str(g) for g in v or ())) for k, v in layers.items()),
        min_layers=int(tests["min_layers"]) if tests.get("min_layers") is not None else None,
        evidence_fields=tuple(str(f) for f in tests["evidence_fields"] or ())
        if "evidence_fields" in tests
        else EvidenceInputs.evidence_fields,
        infer_depth=_infer_depth(tests),
        contexts=str(tests["contexts"]) if tests.get("contexts") else None,
        traces=_strings(tests, "traces", (), "tests", problems),
    )


## @brief The call-graph inference depth a `tests` block declares.
## @param tests The block.
## @return None (omitted: the full transitive closure), or the declared cap (0 = off).
## @version 1
## @utility
def _infer_depth(tests: dict[str, Any]) -> int | None:
    """@brief Read the cap. @return Depth or None."""
    raw = tests.get("infer_depth")
    return None if raw is None else int(raw)


## @brief A (format, path) pair from a validated `results` entry.
## @param e The entry.
## @return The pair.
## @version 1
## @utility
def _result(e: dict[str, Any]) -> tuple[str, str]:
    """@brief Build. @return Pair."""
    return (str(e["format"]), str(e["path"]))


## @brief The theme block.
## @param raw The `theme` mapping.
## @param problems Accumulated problems; appended to.
## @return The spec.
## v2 (2.0.0): readable palette tokens mapped to the CSS names; old abbreviations refused.
## @version 2
## @utility
def _theme(raw: Any, problems: list[str]) -> ThemeSpec:
    """A PALETTE TOKEN THE THEME DOES NOT DEFINE is a problem: it would be a silent no-op.

    @brief Parse the theme.
    @return Spec.
    """
    problems += _unknown(raw, _THEME, "wiki.theme")
    if not isinstance(raw, dict):
        return ThemeSpec()
    palette = raw.get("palette") or {}
    if not isinstance(palette, dict):
        problems.append("`wiki.theme.palette` must map a token to a colour")
        palette = {}
    problems += [
        f"`wiki.theme.palette`: token {k!r} was renamed {_PALETTE_RENAMED[k]!r} in 2.0.0"
        if k in _PALETTE_RENAMED
        else f"`wiki.theme.palette`: token {k!r} is not a theme token ({', '.join(THEME_TOKENS)})"
        for k in palette
        if k not in PALETTE
    ]
    problems += [
        f"`wiki.theme.palette.{k}`: {v!r} is not a colour value"
        for k, v in palette.items()
        if any(c in str(v) for c in ";{}<>")
    ]
    css = raw.get("css") or ()
    return ThemeSpec(
        name=str(raw.get("name") or "clew"),
        palette=tuple(
            (PALETTE[k], str(v))
            for k, v in palette.items()
            if k in PALETTE and not any(c in str(v) for c in ";{}<>")
        ),
        css=(str(css),) if isinstance(css, str) else tuple(str(c) for c in css),
        logo=str(raw["logo"]) if raw.get("logo") else None,
        fonts=bool(raw.get("fonts", True)),
    )


## @brief The declared issue tracker.
## @param raw The `issues` value: {github: owner/repo}, {ado: org/project}, false, or absent.
## @param problems Appended to.
## @return (provider, project), or None when not declared.
## v2: `fetch` beside or instead of a tracker (P3a).
## @version 2
## @utility
def _issues(raw: Any, problems: list[str]) -> tuple[str, str] | None:
    """`fetch` MAY STAND ALONE (the tracker then comes from the origin remote) or beside one
    tracker; two trackers, or an unknown key, is a problem.

    @brief Parse the tracker.
    @return Target or None.
    """
    if raw is None or raw is False:
        return None
    trackers = [k for k in raw if k in ("github", "ado")] if isinstance(raw, dict) else []
    if not isinstance(raw, dict) or set(raw) - {"github", "ado", "fetch"} or len(trackers) > 1:
        problems.append(
            "`wiki.issues` must be {github: owner/repo} or {ado: org/project}, optionally with "
            "`fetch: true`, or false"
        )
        return None
    if not trackers:
        return None
    provider, project = trackers[0], raw[trackers[0]]
    if not isinstance(project, str) or project.count("/") != 1:
        problems.append(f"`wiki.issues.{provider}` must name `<owner-or-org>/<repo-or-project>`")
        return None
    return str(provider), project


## @brief `wiki.check`: the opt-in EARS badge.
## @param raw The `check` value, or None.
## @param problems Collects a problem for a malformed section.
## @return Whether EARS is on.
## @version 1
## @req REQ-DDB-WIKI-042
def _ears(raw: Any, problems: list[str]) -> bool:
    """A BOOLEAN, REFUSED OTHERWISE: `ears: 'yes'` is a problem rather than a truthy string, so a
    typo cannot turn the badge on or off silently.

    @brief Parse `check.ears`.
    @return On or off.
    """
    if raw is None:
        return False
    if (
        not isinstance(raw, dict)
        or set(raw) - {"ears"}
        or not isinstance(raw.get("ears", False), bool)
    ):
        problems.append("`wiki.check` must be {ears: true|false}; `wiki.check.ears` is a boolean")
        return False
    return bool(raw.get("ears", False))


## @brief The doc tags the gate section declares (`guard.validate.extra_tags`), names only.
## @param path The config file.
## @return Tag names without `@`.
## @version 1
## @utility
def _doc_tags(path: Path) -> tuple[str, ...]:
    """@brief Read the declared tags. @return Names."""
    validate = (_top_level(path, "guard").get("validate") or {}) if path else {}
    tags = validate.get("extra_tags") if isinstance(validate, dict) else None
    return tuple(str(t).lstrip("@") for t in tags) if isinstance(tags, list) else ()


## @brief A positive whole number setting, refused by name otherwise.
## @param raw The section.
## @param key The key.
## @param default The default.
## @param problems Collects the problem.
## @return The value, or the default.
## @version 1
## @utility
def _positive(raw: dict, key: str, default: int, problems: list[str]) -> int:
    """@brief Positive int. @return Value."""
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        problems.append(f"`wiki.{key}` must be a whole number of 1 or more, got {value!r}")
        return default
    return value


## The `test_pages` settings, the first the default.
TEST_PAGES = ("linked", "all", "none")


## @brief A key whose value must be one of a fixed set; the first is the default.
## @param raw The section.
## @param key The key.
## @param allowed The allowed values, default first.
## @param problems Collects a problem naming the key and the allowed values.
## @return The value, or the default.
## @version 1
## @utility
def _one_of(raw: dict, key: str, allowed: tuple[str, ...], problems: list[str]) -> str:
    """@brief Enumerated value, refused by name. @return Value."""
    value = raw.get(key)
    if value is None:
        return allowed[0]
    if value not in allowed:
        problems.append(f"`wiki.{key}` must be one of {', '.join(allowed)}, got {value!r}")
        return allowed[0]
    return str(value)


## @brief `wiki.sbom`: which SBOM files to render, and the accepted-licence list.
## @param raw The `sbom` value, or None.
## @param problems Collects a problem for a malformed section.
## @return `sbom_files` / `sbom_accepted` overrides (only what is declared).
## @version 1
## @req REQ-DDB-WIKI-051
def _sbom(raw: Any, problems: list[str]) -> dict[str, tuple[str, ...]]:
    """LISTS, REFUSED OTHERWISE, and an unknown key is named: `files: sbom.json` (a string) would
    otherwise be iterated as characters.

    @brief Parse `sbom`.
    @return Overrides.
    """
    if raw is None:
        return {}
    out: dict[str, tuple[str, ...]] = {}
    keys = {"files": "sbom_files", "accepted": "sbom_accepted"}
    if not isinstance(raw, dict) or set(raw) - set(keys):
        problems.append("`wiki.sbom` must be {files: [globs], accepted: [licence ids]}")
        return {}
    for key, attr in keys.items():
        if key in raw:
            if isinstance(raw[key], list) and all(isinstance(v, str) for v in raw[key]):
                out[attr] = tuple(raw[key])
            else:
                problems.append(f"`wiki.sbom.{key}` must be a list of strings")
    return out


## @brief The declared document kinds.
## @param raw The `doc_kinds` mapping: glob → kind.
## @param problems Appended to.
## @return (glob, kind) pairs, in the order written.
## @version 1
## @utility
def _doc_kinds(raw: Any, problems: list[str]) -> tuple[tuple[str, str], ...]:
    """@brief Parse kinds. @return Pairs."""
    if not isinstance(raw, dict):
        problems.append("`wiki.doc_kinds` must map a path glob to a kind")
        return ()
    out = []
    for glob, kind in raw.items():
        if kind not in DOC_KINDS:
            problems.append(f"`wiki.doc_kinds.{glob}` must be one of {', '.join(DOC_KINDS)}")
            continue
        out.append((str(glob), str(kind)))
    return tuple(out)
