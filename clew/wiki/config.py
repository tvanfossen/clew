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
          file: src/store.py          # the entry's file, when its name is shared
      entry_points: 2                 # every console script / main / thread entry gets a flow of
                                      # this depth (0 = only the declared flows)
      tests:                          # CI evidence for the requirement trace (clew wiki trace)
        junit: [build/junit.xml]
        coverage: build/coverage.xml
        target_only: ["test_hw_*"]
        mutations: build/mutations.yaml   # W9: [{mechanism, test, killed}]
        results:                      # W16: other result formats, each DECLARED
          - {format: ctest, path: build/Testing/Test.xml}   # ctest | tap | catch2 | pytest-json
        gcov: ["build/**/*.gcov", build/cov.json.gz]       # W15: .gcov text or gcov/gcovr JSON
        mapping: docs/req_tests.yaml  # W16: {REQ: [test, ...]} or a `req,test` CSV
        features: ["tests/features/**/*.feature"]          # W16: Gherkin; tags name requirements
        layers:                       # W16: test layers by path / test-id glob
          unit: ["tests/unit/*"]
          bdd: ["tests/features/*"]
        min_layers: 2                 # flag a requirement tested in fewer layers
        evidence_fields: [x-evidence, evidence]  # catalog fields naming test files ([] = off)
        infer_depth: 2                # tests reaching an implementer within N calls (0 = off)
        contexts: build/coverage.json # coverage.py JSON with --cov-context=test (measured links)
      links:
        template: "https://host/repo/blob/{commit}/{file}#L{line}"
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
      theme:                          # W13: the default is clew's own (sassafras-class look)
        name: clew                    # or any installed Sphinx theme (then nothing below applies)
        palette: {acc: "#3D6B2E"}     # override any token of THEME_TOKENS
        css: [docs/wiki.css]          # extra stylesheets, copied into the site
        logo: docs/logo.svg
        fonts: true                   # false: system fonts, no bundled font files
      roadmap: ROADMAP.md             # W17: headings naming a version are burndown milestones
      needs: docs/needs.json          # round 3: Sphinx-needs requirements (the catalog wins)
      impact: docs/generated/impact/impact.json  # default: <guard.output_dir>/impact/impact.json
      components:                     # round 3: the map's boxes; default = packages by path
        Query layer: [clew/query/*]
      issues: {github: owner/repo}    # or {ado: org/project}, or false; default = origin remote
                                      # add `fetch: true` to read open issues at build time

@brief Read and validate the `wiki:` section.
@version 2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

## Every key the section, a flow, the tests block and an audience may carry.
_TOP = {
    "title",
    "docs",
    "flows",
    "tests",
    "links",
    "audiences",
    "sources",
    "catalogs",
    "rules",
    "theme",
    "roadmap",
    "impact",
    "entry_points",
    "components",
    "issues",
    "tooling",
    "test_flows",
    "needs",
}
_THEME = {"name", "palette", "css", "logo", "fonts"}
## The palette tokens of the default theme (the sassafras-class botanical palette).
THEME_TOKENS = (
    "surface",
    "paper",
    "muted",
    "inset",
    "ink",
    "ink2",
    "faint",
    "rule",
    "rule2",
    "acc",
    "accbg",
    "accink",
    "root",
    "rootbg",
    "err",
    "errbg",
    "warn",
    "warnbg",
)
_FLOW = {"entry", "qualified", "depth", "lanes", "stop_at", "title", "animate", "file", "role"}
## The roles a flow is grouped under on the Flows page (round 3, P1e).
FLOW_ROLES = ("product", "threads", "tooling", "tests")
## Paths whose entry points are tooling, unless `wiki.tooling` says otherwise.
DEFAULT_TOOLING = ("scripts/*", "acceptance/*", "tools/*", "benchmarks/*", "examples/*")
_TESTS = {
    "junit",
    "coverage",
    "target_only",
    "mutations",
    "results",
    "gcov",
    "mapping",
    "features",
    "layers",
    "min_layers",
    "evidence_fields",
    "infer_depth",
    "contexts",
}
_RESULT = {"format", "path"}
_SOURCE = {"name", "path", "items", "id", "doc", "req"}
_CATALOG = {"name", "repo", "pin", "catalog"}
_RULE = {"id", "title", "status", "url", "requirements"}
_LINKS = {"template"}
_AUDIENCE = {"exclude_bodies", "exclude_requirement_text"}
## Prose read when the section names none.
DEFAULT_DOCS = ("README.md", "docs/**/*.md", "docs/**/*.rst")


## @brief One flow the site derives.
## v2: `animate` (W12).
## v3: `file` — the entry's file, when its name is shared (every `def main`).
## @version 3
@dataclass(frozen=True)
class FlowSpec:
    """@brief Entry, selector, file, depth, lanes, stop names, title, animation, role. @version 4"""

    entry: str
    qualified: str | None = None
    depth: int = 3
    lanes: str = "files"
    stop_at: tuple[str, ...] = ()
    title: str = ""
    animate: bool = True
    file: str | None = None
    ## `product`, `threads` or `tooling`; "" = classified by the build (tooling paths, else product).
    role: str = ""


## @brief The W15/W16 evidence imports of `wiki.tests`, as declared (paths relative to the repo).
## v2: `evidence_fields` — catalog fields whose test files link their tests; `infer_depth`
## (call-graph inference) and `contexts` (per-test coverage) — tests need no tag.
## @version 2
@dataclass(frozen=True)
class EvidenceInputs:
    """@brief Reports, gcov, mapping, features, layers, catalog, inference. @version 2"""

    results: tuple[tuple[str, str], ...] = ()
    gcov: tuple[str, ...] = ()
    mapping: str | None = None
    features: tuple[str, ...] = ()
    layers: tuple[tuple[str, tuple[str, ...]], ...] | None = None
    min_layers: int | None = None
    evidence_fields: tuple[str, ...] = ("x-evidence", "evidence")
    infer_depth: int = 2
    contexts: str | None = None


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
## @version 12
@dataclass(frozen=True)
class WikiConfig:
    """@brief The whole `wiki:` section. @version 4"""

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
    inputs: EvidenceInputs = EvidenceInputs()
    theme: ThemeSpec = ThemeSpec()
    roadmap: str | None = None
    impact: str | None = None
    entry_points: int = 2
    components: tuple[tuple[str, tuple[str, ...]], ...] = ()
    ## (provider, project) declared; None = read the origin remote.
    issues: tuple[str, str] | None = None
    ## False when `issues: false` — no issue links at all.
    issues_enabled: bool = True
    ## True when `issues.fetch` asks the build to read open issues (the build's only network use).
    issues_fetch: bool = False
    ## Path globs whose entry points are tooling flows.
    tooling: tuple[str, ...] = DEFAULT_TOOLING
    ## The most directly linked tests drawn as flows.
    test_flows: int = 50
    ## A Sphinx-needs `needs.json` contributing requirements (repo-relative), or None.
    needs: str | None = None


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
## @version 12
## @req REQ-DDB-WIKI-003
def load_wiki_config(
    repo_root: Path, config_path: Path | None = None
) -> tuple[WikiConfig, list[str]]:
    """A MISSING SECTION IS A VALID ONE: defaults (the README and docs/ prose, no flows) apply, so a
    repository can build a site before it has written a line of configuration.

    @brief Load the section.
    @return Config and problems.
    @version 12
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
        inputs=_inputs(tests, problems),
        theme=_theme(raw.get("theme") or {}, problems),
        roadmap=str(raw["roadmap"]) if raw.get("roadmap") else None,
        impact=str(raw["impact"]) if raw.get("impact") else None,
        entry_points=int(raw.get("entry_points", 2) or 0),
        components=_components(raw.get("components") or {}, problems),
        issues=_issues(raw.get("issues"), problems),
        issues_enabled=raw.get("issues") is not False,
        issues_fetch=isinstance(raw.get("issues"), dict) and bool(raw["issues"].get("fetch")),
        tooling=tuple(str(g) for g in raw.get("tooling", DEFAULT_TOOLING) or ()),
        test_flows=int(raw.get("test_flows", 50) or 0),
        needs=str(raw["needs"]) if raw.get("needs") else None,
    )
    return config, problems


## @brief The declared component groupings, in the order written.
## @param raw The `components` mapping.
## @param problems Appended to.
## @return (name, globs) pairs.
## @version 1
## @dg_internal
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
## v3: `file`.
## v4: `role` (one of FLOW_ROLES).
## @version 4
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
        file=str(raw["file"]) if raw.get("file") else None,
        role=_role(raw.get("role"), where, problems),
    )


## @brief A flow's declared role, checked.
## @param raw The value, or None.
## @param where The flow's location, for the problem text.
## @param problems Appended to.
## @return The role, or "" when undeclared or unknown.
## @version 1
## @dg_internal
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
## @version 2
## @dg_internal
def _inputs(tests: dict[str, Any], problems: list[str]) -> EvidenceInputs:
    """A RESULT FORMAT IS DECLARED, so an entry without one is a problem, never a sniffed guess.

    @brief Parse imports.
    @return Inputs.
    @version 2
    """
    from .imports import RESULT_FORMATS

    results = _entries(tests, "results", _RESULT, ("format", "path"), _result, problems)
    problems += [
        f"`wiki.tests.results`: format {fmt!r} is not known ({', '.join(RESULT_FORMATS)})"
        for fmt, _path in results
        if fmt not in RESULT_FORMATS
    ]
    layers = tests.get("layers")
    if layers is not None and not isinstance(layers, dict):
        problems.append("`wiki.tests.layers` must map a layer name to path globs")
        layers = None
    gcov = tests.get("gcov") or ()
    return EvidenceInputs(
        results=results,
        gcov=(str(gcov),) if isinstance(gcov, str) else tuple(str(g) for g in gcov),
        mapping=str(tests["mapping"]) if tests.get("mapping") else None,
        features=tuple(str(f) for f in tests.get("features") or ()),
        layers=None
        if layers is None
        else tuple((str(k), tuple(str(g) for g in v or ())) for k, v in layers.items()),
        min_layers=int(tests["min_layers"]) if tests.get("min_layers") else None,
        evidence_fields=tuple(str(f) for f in tests["evidence_fields"] or ())
        if "evidence_fields" in tests
        else EvidenceInputs.evidence_fields,
        infer_depth=int(tests.get("infer_depth", EvidenceInputs.infer_depth) or 0),
        contexts=str(tests["contexts"]) if tests.get("contexts") else None,
    )


## @brief A (format, path) pair from a validated `results` entry.
## @param e The entry.
## @return The pair.
## @version 1
## @dg_internal
def _result(e: dict[str, Any]) -> tuple[str, str]:
    """@brief Build. @return Pair."""
    return (str(e["format"]), str(e["path"]))


## @brief The theme block.
## @param raw The `theme` mapping.
## @param problems Accumulated problems; appended to.
## @return The spec.
## @version 1
## @dg_internal
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
        f"`wiki.theme.palette`: token {k!r} is not a theme token ({', '.join(THEME_TOKENS)})"
        for k in palette
        if k not in THEME_TOKENS
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
            (str(k), str(v))
            for k, v in palette.items()
            if k in THEME_TOKENS and not any(c in str(v) for c in ";{}<>")
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
## @dg_internal
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
