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

Sphinx is imported only inside `_render`, so the rest of `clew.wiki` — `check` above all — runs
without the extra installed.

@brief Generate and render the wiki site.
@version 1
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Audience, FlowSpec, WikiConfig, load_wiki_config
from .flow import Flow, derive_flow
from .svg import flow_svg


## @brief Build the site for a repository.
## @param repo_root The repository.
## @param db Its index.
## @param out_dir Output directory; `<out_dir>/html` is the site.
## @param audience An audience name from `wiki.audiences`, or None for the full site.
## @return The rendered site's directory.
## @version 1
## @req REQ-DDB-WIKI-003
def build_wiki(repo_root: Path, db: Path, out_dir: Path, audience: str | None = None) -> Path:
    """REFUSES rather than degrades: an invalid section, an unknown audience or a missing extra is
    an error naming itself, never a partial site that looks complete.

    @brief Write and render the site.
    @return The HTML directory.
    @version 1
    """
    repo_root, out_dir = Path(repo_root), Path(out_dir)
    config, problems = load_wiki_config(repo_root)
    if problems:
        raise ValueError("wiki configuration problems: " + "; ".join(problems))
    rules = _audience(config, audience)
    source = out_dir / "_source"
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    pages = _prose(repo_root, config, source)
    pages += [_flow_page(repo_root, db, spec, source, rules, config) for spec in config.flows]
    pages.append(_requirements_page(repo_root, db, config, source, rules))
    _write_index(source, config.title, pages)
    return _render(source, out_dir / "html", config.title)


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


## @brief Write one flow page: diagram, steps, and the bodies the flow reaches.
## @param repo_root The repository.
## @param db The index.
## @param spec The flow.
## @param source The Sphinx source directory.
## @param rules The audience rules.
## @param config The section (for the link template).
## @return The page name.
## @version 1
## @dg_internal
def _flow_page(
    repo_root: Path, db: Path, spec: FlowSpec, source: Path, rules: Audience, config: WikiConfig
) -> str:
    """@brief Render one flow page. @return Page name."""
    flow = derive_flow(
        db,
        repo_root,
        spec.entry,
        qualified=spec.qualified,
        depth=spec.depth,
        lanes=spec.lanes,
        stop_at=spec.stop_at,
    )
    name = f"flow-{spec.entry}"
    lines = [
        f"# {spec.title or 'Flow: ' + spec.entry}",
        "",
        "```{raw} html",
        flow_svg(flow),
        "```",
        "",
        "| # | caller | callee | frames | where |",
        "|---|---|---|---|---|",
    ]
    commit = _commit(repo_root)
    for i, step in enumerate(flow.steps, start=1):
        frames = " ".join(f.kind for f in step.frames)
        where = _link(config.link_template, commit, step.file, step.line)
        lines.append(f"| {i} | `{step.caller}` | `{step.callee}` | {frames} | {where} |")
    if not rules.exclude_bodies:
        lines += _bodies(db, repo_root, flow)
    (source / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return name


## @brief The source bodies of every function a flow reaches, as code blocks.
## @param db The index.
## @param repo_root The repository.
## @param flow The flow.
## @return Markdown lines.
## @version 1
## @dg_internal
def _bodies(db: Path, repo_root: Path, flow: Flow) -> list[str]:
    """THE INDEX'S OWN BODY EXCERPT (export_dossier), so a page shows what `dossier` shows.

    @brief Body sections.
    @return Lines.
    """
    from ..query import export_dossier

    seen: list[tuple[str, str]] = [(flow.entry, flow.entry_qualified)]
    seen += [(s.callee, s.callee_qualified) for s in flow.steps if s.callee_qualified]
    out: list[str] = ["", "## Functions", ""]
    for name, qual in dict.fromkeys(seen):
        payload = export_dossier(db, name, qualified=qual or None, repo_root=repo_root)
        body = payload.get("body") or {}
        if not body.get("lines"):
            continue
        out += [
            f"### `{qual or name}`",
            "",
            f"`{body.get('file', '')}`",
            "",
            "```",
            *body["lines"],
            "```",
            "",
        ]
    return out


## @brief Write the requirement trace page.
## @param repo_root The repository.
## @param db The index.
## @param config The section.
## @param source The Sphinx source directory.
## @param rules The audience rules.
## @return The page name.
## @version 1
## @dg_internal
def _requirements_page(
    repo_root: Path, db: Path, config: WikiConfig, source: Path, rules: Audience
) -> str:
    """@brief Render the trace. @return Page name."""
    from .evidence import requirement_evidence

    rows = requirement_evidence(
        db,
        junit=[repo_root / j for j in config.junit],
        coverage=(repo_root / config.coverage) if config.coverage else None,
        target_only=config.target_only,
    )
    lines = ["# Requirements", "", "| requirement | tier | title | tests |", "|---|---|---|---|"]
    for row in rows:
        title = "" if rules.exclude_requirement_text else row.title
        tests = ", ".join(f"`{t}` ({s})" for t, s in row.tests)
        lines.append(f"| {row.req_id} | **{row.tier}** | {title} | {tests} |")
    (source / "requirements.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "requirements"


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
## @param title The project title.
## @return The output directory.
## @version 1
## @dg_internal
def _render(source: Path, html: Path, title: str) -> Path:
    """THE ONLY SPHINX IMPORT, so everything else runs without the extra.

    @brief Run sphinx-build.
    @return HTML dir.
    """
    try:
        from sphinx.cmd.build import build_main
    except ImportError as exc:
        raise ValueError(
            "clew wiki build needs the wiki extra: pip install 'clew-trace[wiki]'"
        ) from exc
    (source / "conf.py").write_text(
        f"project = {title!r}\n"
        "extensions = ['myst_parser']\n"
        "source_suffix = {'.rst': 'restructuredtext', '.md': 'markdown'}\n"
        "html_theme = 'alabaster'\n"
        "exclude_patterns = ['_build']\n",
        encoding="utf-8",
    )
    if build_main(["-q", "-b", "html", str(source), str(html)]) != 0:
        raise ValueError(f"sphinx-build failed for {source}")
    return html
