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
## v4: sections (Docs / Flows / Requirements / Model entries) instead of one page per top-bar
## entry; the trace from every source (catalog, impact.json) on one requirements page.
## v5: entry-point flows beside the declared ones.
## v6: sections ordered Requirements · Flows · Docs · Model entries — requirements front and
## centre (round 3, P1b; Change impact and Map slot in after Flows when they land).
## v7: the system map (round 3, P1c) after Flows.
## @version 7
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
    @version 6
    """
    from .flowpage import flow_page
    from .graph import build_graph
    from .mappage import map_page
    from .tracepages import Trace, nodes_page, requirements_page
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
    commit = _commit(repo_root)
    trace = Trace.gather(repo_root, db, config, commit)
    snapshot = trace.snapshot(version or "")
    milestones = _milestones(repo_root, config)
    burndown = _burndown(out_dir, version, snapshot, milestones) if version else ""
    pages = [
        flow_page(repo_root, db, spec, source, rules, config, commit)
        for spec in _all_flows(repo_root, db, config)
    ]
    flows = [p.name for p in pages]
    graph = build_graph(db, trace.evidence, trace.impact, config.components, exclude_tests=True)
    sections = [
        requirements_page(trace, config, source, rules, burndown),
        _section(source, "flows", "Flows", flows, _FLOWS_LEAD),
        map_page(graph, {p.name: (p.title, set(p.files)) for p in pages}, source),
        _section(source, "docs", "Docs", _prose(repo_root, config, source), _DOCS_LEAD),
    ]
    if config.sources:
        sections.append(nodes_page(trace, config, source))
    _write_index(source, config, trace, [s for s in sections if s], len(flows))
    html = _render(source, site_dir / "html", config, repo_root)
    if version:
        record_version(out_dir, version, snapshot, config.title, milestones)
    return html


## @brief The declared flows, then every entry point's flow not already declared.
## @param repo_root The repository.
## @param db The index.
## @param config The section.
## @return Flow specs.
## @version 1
## @dg_internal
def _all_flows(repo_root: Path, db: Path, config: WikiConfig) -> list:
    """A DECLARED FLOW WINS for its function: its title, depth and lanes are the repository's
    choice, so the derived one for the same entry is dropped.

    @brief Declared + entry-point flows.
    @return Specs.
    """
    from .entrypoints import entry_point_flows

    specs = list(config.flows)
    if config.entry_points > 0:
        declared = {(s.entry, s.file) for s in specs} | {(s.entry, None) for s in specs}
        specs += [
            s
            for s in entry_point_flows(db, repo_root, config.entry_points)
            if (s.entry, s.file) not in declared and (s.entry, None) not in declared
        ]
    return specs


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
## @return Page names, in configured order.
## v2: `.html` prose — its body is embedded in a themed page (owner 2026-11-15: user-selected
## html / md content).
## @version 2
## @dg_internal
def _prose(repo_root: Path, config: WikiConfig, source: Path) -> list[str]:
    """AS WRITTEN: Markdown through MyST, reStructuredText natively, HTML embedded as it is.

    @brief Copy prose.
    @return Page names.
    """
    pages: list[str] = []
    for pattern in config.docs:
        for path in sorted(repo_root.glob(pattern)):
            suffix = path.suffix.lower()
            if not path.is_file() or suffix not in (".md", ".rst", ".html", ".htm"):
                continue
            rel = path.relative_to(repo_root)
            target = source / "prose" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if suffix in (".html", ".htm"):
                target = target.with_suffix(".md")
                target.write_text(_html_page(path), encoding="utf-8")
            else:
                shutil.copyfile(path, target)
            page = str(Path("prose") / rel.with_suffix(""))
            if page not in pages:
                pages.append(page)
    return pages


## @brief An HTML document as a page: its title as the heading, its body embedded.
## @param path The document.
## @return MyST text.
## @version 1
## @dg_internal
def _html_page(path: Path) -> str:
    """@brief Embed HTML. @return Page text."""
    import re

    doc = path.read_text(encoding="utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", doc, re.S | re.I)
    body = re.search(r"<body[^>]*>(.*)</body>", doc, re.S | re.I)
    heading = (title.group(1).strip() if title else "") or path.stem
    return f"# {heading}\n\n```{{raw}} html\n{(body.group(1) if body else doc).strip()}\n```\n"


_DOCS_LEAD = "The repository's own documentation, as written."
_FLOWS_LEAD = (
    "Sequence diagrams derived from the index: every step is a call the index resolved, in the "
    "caller's source order. Click a step for the data it carries."
)


## @brief A section page listing its children; nothing when it has none.
## @param source The Sphinx source directory.
## @param name The page name.
## @param title The section title (the top-bar label).
## @param children Child page names.
## @param lead The section's one-line description.
## @return The page name, or "" when there are no children.
## @version 1
## @dg_internal
def _section(source: Path, name: str, title: str, children: list[str], lead: str) -> str:
    """@brief Write a section page. @return Page name or ""."""
    if not children:
        return ""
    text = [f"# {title}", "", lead, "", "```{toctree}", ":maxdepth: 1", "", *children, "```", ""]
    (source / f"{name}.md").write_text("\n".join(text), encoding="utf-8")
    return name


## @brief Write the home page: a card per section, and the toctree the top bar is built from.
## @param source The Sphinx source directory.
## @param config The section (title).
## @param trace The gathered trace (the requirements card's counts).
## @param sections Section page names, in order.
## @param flow_count How many flow pages were written (declared and entry-point).
## @return None.
## v2: section cards; the top bar names sections, not every page (owner 2026-11-15).
## v3: each card carries its section's icon (round 3, P1b); the flows card counts every flow page,
## not only the declared ones (it read "2" on a site with 30).
## v4: the map card (round 3, P1c).
## @version 4
## @dg_internal
def _write_index(
    source: Path, config: WikiConfig, trace: object, sections: list[str], flow_count: int
) -> None:
    """@brief Root page. @return None."""
    from html import escape

    from .icons import icon

    ev = trace.evidence
    blurbs = {
        "docs": ("Docs", "The repository's own documentation."),
        "flows": ("Flows", f"{flow_count} sequence diagrams derived from the index."),
        "requirements": (
            "Requirements",
            f"{len(ev)} requirements · {sum(1 for r in ev if r.implementers)} implemented · "
            f"{sum(1 for r in ev if r.tests)} tested · {sum(1 for r in ev if r.tier == 'PASS')} "
            "passing.",
        ),
        "nodes": ("Model entries", "Entries of declared model files and the code realising them."),
        "map": ("Map", "The system's components, how they call each other, and what each holds."),
    }
    cards = "".join(
        f'<a class="card-link" href="{name}.html"><h3>{icon(name, 22)}'
        f"{escape(blurbs[name][0])}</h3><p>{escape(blurbs[name][1])}</p></a>"
        for name in sections
    )
    text = [
        f"# {config.title}",
        "",
        "```{raw} html",
        f'<div class="cards">{cards}</div>',
        "```",
        "",
        "```{toctree}",
        ":hidden:",
        ":maxdepth: 1",
        "",
        *sections,
        "```",
        "",
    ]
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
