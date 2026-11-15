# SPDX-License-Identifier: MIT
"""`clew wiki build`: a self-contained static site, rendered by Sphinx + MyST.

1.4.0 Track 4, W5 and W6 (owner 2026-11-13: Sphinx + MyST behind the `clew-trace[wiki]` extra).
The build writes a Sphinx source tree — the repository's own prose copied as written, one page
per configured flow (an inline SVG diagram, the step table and the bodies of the functions it
reaches), and the requirement trace with its evidence tiers — then renders it with Sphinx's
built-in theme, whose assets ship inside Sphinx: no CDN, no runtime fetch.

AUDIENCES ARE A PROPERTY OF THE BUILD (W6). `--audience NAME` applies that audience's rules from
`wiki.audiences`: `exclude_bodies` writes no function body anywhere, `exclude_requirement_text`
no requirement titles. The tests assert redaction on the rendered HTML, not on a flag.

The trace page carries the W7–W9 targets: the nodes a requirement's model entries name, the
external rules that map onto requirements (rule → requirement → function → test), each pinned
sub-catalog's rows at their pin, and mutation outcomes. A `nodes` page lists every external node
with the functions that realise it.

VERSION-KEYED SITES (W11): `version=KEY` writes the site to `<out>/<KEY>/html`, records a snapshot
of what it traced (`<out>/<KEY>/site.json`), and refreshes `<out>/versions.json` and the
`<out>/index.html` that lists every version — see `clew.wiki.versions`.

Sphinx is imported only inside `_render`, so the rest of `clew.wiki` — `check` above all — runs
without the extra installed.

@brief Generate and render the wiki site.
@version 2
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Audience, WikiConfig, load_wiki_config

## Markdown table cells may not carry a bare pipe or newline.
_CELL = str.maketrans({"|": "\\|", "\n": " "})


## @brief Build the site for a repository.
## @param repo_root The repository.
## @param db Its index.
## @param out_dir Output directory; `<out_dir>/html` is the site.
## @param audience An audience name from `wiki.audiences`, or None for the full site.
## @param version A version key: the site goes to `<out>/<key>/` and is listed in `<out>`.
## @param config_path A file whose `wiki:` section applies instead of the repository's.
## @return The rendered site's directory.
## v2: nodes page, rules / catalogs / mutations on the trace, version-keyed output, config_path.
## v3: theme (W13), summary + charts (W14), burndown (W17), interactive flow pages (W18).
## @version 3
## @req REQ-DDB-WIKI-003
def build_wiki(
    repo_root: Path,
    db: Path,
    out_dir: Path,
    audience: str | None = None,
    version: str | None = None,
    config_path: Path | None = None,
) -> Path:
    """REFUSES rather than degrades: an invalid section, an unknown audience or a missing extra is
    an error naming itself, never a partial site that looks complete.

    @brief Write and render the site.
    @return The HTML directory.
    @version 3
    """
    from .flowpage import flow_page
    from .summary import summary_page
    from .versions import record_version, valid_key

    repo_root, out_dir = Path(repo_root), Path(out_dir)
    config, problems = load_wiki_config(repo_root, config_path)
    if problems:
        raise ValueError("wiki configuration problems: " + "; ".join(problems))
    rules = _audience(config, audience)
    site_dir = out_dir / valid_key(version) if version else out_dir
    source = site_dir / "_source"
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    trace = _Trace.gather(repo_root, db, config)
    commit = _commit(repo_root)
    snapshot = trace.snapshot(version or "", commit)
    milestones = _milestones(repo_root, config)
    burndown = _burndown(out_dir, version, snapshot, milestones) if version else ""
    pages = _prose(repo_root, config, source)
    pages.append(summary_page(trace.evidence, config.inputs.min_layers, source, burndown))
    pages += [
        flow_page(repo_root, db, spec, source, rules, config, commit) for spec in config.flows
    ]
    pages.append(_requirements_page(trace, config, source, rules))
    if trace.nodes:
        pages.append(_nodes_page(trace, source))
    _write_index(source, config.title, pages)
    html = _render(source, site_dir / "html", config, repo_root)
    if version:
        record_version(out_dir, version, snapshot, config.title, milestones)
    return html


## @brief The roadmap's milestones, or none when no roadmap is declared.
## @param repo_root The repository.
## @param config The section.
## @return (version, heading) pairs.
## @version 1
## @dg_internal
def _milestones(repo_root: Path, config: WikiConfig) -> list[tuple[str, str]]:
    """@brief Read milestones. @return Pairs."""
    from .charts import roadmap_milestones

    return roadmap_milestones(repo_root / config.roadmap) if config.roadmap else []


## @brief The burndown for a versioned build: earlier recorded versions, then this one.
## @param out_dir The versioned output root.
## @param version This build's key.
## @param snapshot This build's snapshot.
## @param milestones Roadmap milestones.
## @return SVG markup.
## @version 1
## @dg_internal
def _burndown(out_dir: Path, version: str, snapshot: dict, milestones: list) -> str:
    """@brief Draw the burndown. @return SVG."""
    from .charts import burndown
    from .versions import series

    return burndown(series(out_dir, version, snapshot), milestones)


## @brief Everything the trace page and the version snapshot are drawn from, gathered once.
## @version 1
class _Trace:
    """@brief Evidence rows, nodes and their references, catalogs, rules. @version 1"""

    ## @brief Hold the gathered parts.
    ## @param evidence Requirement evidence rows.
    ## @param nodes External nodes.
    ## @param refs Node address → referencing functions.
    ## @param catalogs Pinned catalog rows per catalog.
    ## @param config The section (rules).
    ## @dg_internal
    ## @version 1
    def __init__(self, evidence, nodes, refs, catalogs, config: WikiConfig) -> None:
        """@brief Store. @return None."""
        self.evidence = evidence
        self.by_id = {r.req_id: r for r in evidence}
        self.nodes = nodes
        self.refs = refs
        self.catalogs = catalogs
        self.rules = config.rules

    ## @brief Gather the trace for a repository.
    ## @param repo_root The repository.
    ## @param db The index.
    ## @param config The section.
    ## @return The trace.
    ## v2: each catalog carries its pin problems, so the page states what `check` found.
    ## v3: the W15/W16 evidence imports.
    ## @dg_internal
    ## @version 3
    @classmethod
    def gather(cls, repo_root: Path, db: Path, config: WikiConfig) -> _Trace:
        """@brief Read evidence, nodes and catalogs. @return Trace."""
        from .catalogs import catalog_requirements, pin_problems
        from .evidence import requirement_evidence
        from .sources import load_nodes, node_references

        evidence = requirement_evidence(
            db,
            junit=[repo_root / j for j in config.junit],
            coverage=(repo_root / config.coverage) if config.coverage else None,
            target_only=config.target_only,
            mutations=(repo_root / config.mutations) if config.mutations else None,
            inputs=config.inputs,
            repo_root=repo_root,
        )
        nodes, _ = load_nodes(repo_root, config.sources)
        catalogs = [
            (spec, catalog_requirements(repo_root, spec)[0], pin_problems(repo_root, spec))
            for spec in config.catalogs
        ]
        return cls(evidence, nodes, node_references(db), catalogs, config)

    ## @brief The nodes that serve a requirement.
    ## @param req_id The requirement.
    ## @return Node addresses.
    ## @dg_internal
    ## @version 1
    def nodes_for(self, req_id: str) -> list[str]:
        """@brief Look up. @return Addresses."""
        return [n.ref for n in self.nodes if req_id in n.requirements]

    ## @brief The snapshot a version-keyed build records.
    ## @param key The version key.
    ## @param commit The commit described.
    ## @return Plain data.
    ## @dg_internal
    ## @version 1
    def snapshot(self, key: str, commit: str) -> dict:
        """@brief Snapshot. @return Data."""
        return {
            "key": key,
            "commit": commit,
            "requirements": {r.req_id: r.tier for r in self.evidence},
            "nodes": sorted(n.ref for n in self.nodes),
        }


## @brief The rules for the requested audience.
## @param config The section.
## @param audience The name, or None.
## @return The rules.
## @version 1
## @dg_internal
def _audience(config: WikiConfig, audience: str | None) -> Audience:
    """@brief Resolve an audience. @return Rules."""
    if audience is None:
        return Audience()
    if audience not in config.audiences:
        known = ", ".join(sorted(config.audiences)) or "none declared"
        raise ValueError(f"unknown audience {audience!r} (known: {known})")
    return config.audiences[audience]


## @brief Copy the configured prose into the source tree.
## @param repo_root The repository.
## @param config The section.
## @param source The Sphinx source directory.
## @return Page names (without suffix) for the toctree.
## @version 1
## @dg_internal
def _prose(repo_root: Path, config: WikiConfig, source: Path) -> list[str]:
    """AS WRITTEN: Markdown through MyST, reStructuredText natively.

    @brief Copy prose.
    @return Page names.
    """
    pages: list[str] = []
    for pattern in config.docs:
        for path in sorted(repo_root.glob(pattern)):
            if not path.is_file() or path.suffix.lower() not in (".md", ".rst"):
                continue
            rel = path.relative_to(repo_root)
            target = source / "prose" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            page = str(Path("prose") / rel.with_suffix(""))
            if page not in pages:
                pages.append(page)
    return pages


## @brief Write the requirement trace page.
## @param trace The gathered trace.
## @param config The section.
## @param source The Sphinx source directory.
## @param rules The audience rules.
## @return The page name.
## v2: nodes and mutations per requirement; rules; pinned catalogs.
## v3: tier / test charts, status tags, test layers (W14/W16).
## @version 3
## @dg_internal
def _requirements_page(trace: _Trace, config: WikiConfig, source: Path, rules: Audience) -> str:
    """@brief Render the trace. @return Page name."""
    from .summary import charts_block

    lines = [
        "# Requirements",
        "",
        "```{raw} html",
        charts_block(trace.evidence),
        "```",
        "",
        "| requirement | tier | title | tests | layers | nodes | mutations |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in trace.evidence:
        title = "" if rules.exclude_requirement_text else _cell(row.title)
        tests = ", ".join(f"`{_cell(t)}` {_tag(s)}" for t, s in row.tests)
        layers = ", ".join(f"{k} {n}" for k, n in row.layers or ())
        nodes = ", ".join(f"`{n}`" for n in trace.nodes_for(row.req_id))
        mutations = ", ".join(f"`{m}`→`{t}` {o}" for m, t, o in row.mutations or ())
        lines.append(
            f"| {row.req_id} | {_tag(row.tier)} | {title} | {tests} | {layers} | {nodes} "
            f"| {mutations} |"
        )
    lines += _rules_section(trace, rules)
    lines += _catalogs_section(trace, rules)
    (source / "requirements.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "requirements"


## @brief The rule → requirement → function → test chain.
## @param trace The gathered trace.
## @param rules The audience rules.
## @return Markdown lines; [] when no rule is declared.
## @version 1
## @dg_internal
def _rules_section(trace: _Trace, rules: Audience) -> list[str]:
    """@brief Rules table. @return Lines."""
    if not trace.rules:
        return []
    lines = [
        "",
        "## Rules",
        "",
        "| rule | status | title | requirement | tier | functions | tests |",
        "|---|---|---|---|---|---|---|",
    ]
    for rule in trace.rules:
        rule_id = f"[{rule.id}]({rule.url})" if rule.url else rule.id
        title = "" if rules.exclude_requirement_text else _cell(rule.title)
        for req_id in rule.requirements or ("",):
            row = trace.by_id.get(req_id)
            tier = row.tier if row else "MISSING"
            impls = ", ".join(f"`{n}`" for n in (row.implementers if row else ()))
            tests = ", ".join(f"`{t}` ({s})" for t, s in (row.tests if row else ()))
            lines.append(
                f"| {rule_id} | {rule.status} | {title} | {req_id} | **{tier}** | {impls} | {tests} |"
            )
    return lines


## @brief Each pinned sub-catalog's rows, at their pin.
## @param trace The gathered trace.
## @param rules The audience rules.
## @return Markdown lines; [] when no catalog is declared.
## v2: states each catalog's pin problems.
## @version 2
## @dg_internal
def _catalogs_section(trace: _Trace, rules: Audience) -> list[str]:
    """@brief Catalog tables. @return Lines."""
    lines: list[str] = []
    for spec, rows, problems in trace.catalogs:
        lines += [
            "",
            f"## Catalog `{spec.name}` at `{spec.pin}`",
            "",
            f"Read from `{spec.repo}/{spec.catalog}` at the pin, not the sibling's working tree.",
            "",
            *[f"**Check failure:** {_cell(p)}" + "\n" for p in problems],
            "| requirement | title | tier here | functions here |",
            "|---|---|---|---|",
        ]
        for req in rows:
            row = trace.by_id.get(req.req_id)
            title = "" if rules.exclude_requirement_text else _cell(req.title)
            impls = ", ".join(f"`{n}`" for n in (row.implementers if row else ()))
            lines.append(f"| {req.req_id} | {title} | {row.tier if row else '—'} | {impls} |")
    return lines


## @brief Write the external nodes page.
## @param trace The gathered trace.
## @param source The Sphinx source directory.
## @return The page name.
## @version 1
## @dg_internal
def _nodes_page(trace: _Trace, source: Path) -> str:
    """@brief Render nodes. @return Page name."""
    lines = [
        "# Model nodes",
        "",
        "| node | doc | file | functions | requirements |",
        "|---|---|---|---|---|",
    ]
    for node in trace.nodes:
        funcs = ", ".join(f"`{f}`" for f in trace.refs.get(node.ref, ()))
        reqs = ", ".join(node.requirements)
        lines.append(f"| `{node.ref}` | {_cell(node.doc)} | `{node.file}` | {funcs} | {reqs} |")
    (source / "nodes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "nodes"


## @brief Text made safe for one Markdown table cell.
## @param text The text.
## @return Escaped text.
## @version 1
## @dg_internal
def _cell(text: str) -> str:
    """@brief Escape. @return Text."""
    return text.translate(_CELL)


## @brief A tier or status as a themed tag (MyST passes inline HTML through).
## @param value The tier or status.
## @return HTML.
## @version 1
## @dg_internal
def _tag(value: str) -> str:
    """@brief Tag. @return HTML."""
    return f'<span class="tier t-{value}">{value}</span>'


## @brief Write the root page with its toctree.
## @param source The Sphinx source directory.
## @param title The site title.
## @param pages Page names in order.
## @return None.
## @version 1
## @dg_internal
def _write_index(source: Path, title: str, pages: list[str]) -> None:
    """@brief Root page. @return None."""
    text = [f"# {title}", "", "```{toctree}", ":maxdepth: 1", "", *pages, "```", ""]
    (source / "index.md").write_text("\n".join(text), encoding="utf-8")


## @brief A source link for a file and line, or the bare location when no template is set.
## @param template The link template.
## @param commit The commit the site describes.
## @param rel Repo-relative file.
## @param line Line number.
## @return Markdown.
## @version 1
## @dg_internal
def _link(template: str, commit: str, rel: str, line: int) -> str:
    """@brief Format a link. @return Markdown."""
    where = f"{rel}:{line}"
    if not template or not rel:
        return f"`{where}`"
    return f"[{where}]({template.format(commit=commit, file=rel, line=line)})"


## @brief The repository's HEAD commit, or "HEAD" when it cannot be read.
## @param repo_root The repository.
## @return The full sha.
## @version 1
## @dg_internal
def _commit(repo_root: Path) -> str:
    """FULL IDS, through the hardened git environment (#67: commit-correct links).

    @brief Read HEAD.
    @return Sha.
    """
    from ..gitenv import git_argv

    try:
        out = subprocess.run(
            git_argv("rev-parse", "HEAD"),
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "HEAD"
    return out.stdout.strip() or "HEAD"


## @brief Render the source tree to HTML with Sphinx.
## @param source The Sphinx source directory.
## @param html The output directory.
## @param config The section (title, theme).
## @param repo_root The repository (theme files are relative to it).
## @return The output directory.
## v2: the configured theme (W13), clew's own by default.
## @version 2
## @dg_internal
def _render(source: Path, html: Path, config: WikiConfig, repo_root: Path) -> Path:
    """THE ONLY SPHINX IMPORT, so everything else runs without the extra.

    @brief Run sphinx-build.
    @return HTML dir.
    """
    from .theme import sphinx_settings

    try:
        from sphinx.cmd.build import build_main
    except ImportError as exc:
        raise ValueError(
            "clew wiki build needs the wiki extra: pip install 'clew-trace[wiki]'"
        ) from exc
    settings = {
        "project": config.title,
        "extensions": ["myst_parser"],
        "source_suffix": {".rst": "restructuredtext", ".md": "markdown"},
        "exclude_patterns": ["_build"],
        **sphinx_settings(config.theme, repo_root, source),
    }
    (source / "conf.py").write_text(
        "".join(f"{k} = {v!r}\n" for k, v in settings.items()), encoding="utf-8"
    )
    if build_main(["-q", "-b", "html", str(source), str(html)]) != 0:
        raise ValueError(f"sphinx-build failed for {source}")
    return html
