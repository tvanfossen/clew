# SPDX-License-Identifier: MIT
"""The wiki as Markdown pages for a GitHub or Azure DevOps wiki (round 3, P5b).

Owner 2026-11-15: serve the wiki directly on GH or ADO, replacing a doxygen-to-Pages pipeline. A
wiki host renders Markdown and Mermaid, not a built site, so this writes the pages a wiki takes
as they are — Home, Requirements, Flows (one page per flow, its sequence diagram in Mermaid) and
Change impact — with no Sphinx and no HTML. The map, lenses and ego-graphs need the HTML site and
Home says so rather than leaving them silently out.

The two hosts differ in three places only, so a flavour is a small subclass: how a page links
another, how a Mermaid diagram is fenced, and how page order is given (GitHub's `_Sidebar.md`,
Azure DevOps' `.order`). The audience rules apply as on the HTML site.

@brief Write the wiki as Markdown pages.
@version 1
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

## The flavours, by name.
FLAVORS = ("github", "ado")


## @brief How one wiki host spells links, diagrams and page order.
## @version 1
class _Flavor(ABC):
    """@brief A host's Markdown dialect. @version 1"""

    ## @brief A link to another page.
    ## @param page The page name (no extension).
    ## @param label The link text.
    ## @return Markdown.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def link(self, page: str, label: str) -> str:
        """@brief Link. @return Markdown."""

    ## @brief A Mermaid diagram block.
    ## @param source The Mermaid text.
    ## @return Markdown.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def mermaid(self, source: str) -> str:
        """@brief Diagram. @return Markdown."""

    ## @brief Write the host's page-order file.
    ## @param out The wiki directory.
    ## @param pages (page, label) pairs in order.
    ## @return None.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def order(self, out: Path, pages: list[tuple[str, str]]) -> None:
        """@brief Order. @return None."""


## @brief GitHub wikis.
## @version 1
class _GitHub(_Flavor):
    """@brief GitHub. @version 1"""

    ## @brief Link.
    ## @param page Page.
    ## @param label Text.
    ## @return Markdown.
    ## @version 1
    ## @dg_internal
    def link(self, page: str, label: str) -> str:
        """@brief Link. @return Markdown."""
        return f"[{label}]({page})"

    ## @brief Diagram.
    ## @param source Mermaid.
    ## @return Markdown.
    ## @version 1
    ## @dg_internal
    def mermaid(self, source: str) -> str:
        """@brief Diagram. @return Markdown."""
        return f"```mermaid\n{source.rstrip()}\n```"

    ## @brief `_Sidebar.md`.
    ## @param out Directory.
    ## @param pages Pairs.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def order(self, out: Path, pages: list[tuple[str, str]]) -> None:
        """@brief Sidebar. @return None."""
        lines = [f"- {self.link(page, label)}" for page, label in pages]
        (out / "_Sidebar.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


## @brief Azure DevOps wikis.
## @version 1
class _Ado(_Flavor):
    """@brief Azure DevOps. @version 1"""

    ## @brief Link.
    ## @param page Page.
    ## @param label Text.
    ## @return Markdown.
    ## @version 1
    ## @dg_internal
    def link(self, page: str, label: str) -> str:
        """@brief Link. @return Markdown."""
        return f"[{label}](./{page}.md)"

    ## @brief Diagram.
    ## @param source Mermaid.
    ## @return Markdown.
    ## @version 1
    ## @dg_internal
    def mermaid(self, source: str) -> str:
        """@brief Diagram. @return Markdown."""
        return f"::: mermaid\n{source.rstrip()}\n:::"

    ## @brief `.order`.
    ## @param out Directory.
    ## @param pages Pairs.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def order(self, out: Path, pages: list[tuple[str, str]]) -> None:
        """@brief Order file. @return None."""
        (out / ".order").write_text("\n".join(p for p, _l in pages) + "\n", encoding="utf-8")


## @brief Write the wiki as Markdown pages.
## @param repo_root The repository.
## @param db Its index.
## @param out The wiki directory (created).
## @param flavor `github` or `ado`.
## @param audience An audience from `wiki.audiences`, or None.
## @param config_path A file whose `wiki:` section applies, or None.
## @return The directory.
## @version 1
## @req REQ-DDB-WIKI-038
def build_markdown(
    repo_root: Path,
    db: Path,
    out: Path,
    flavor: str,
    audience: str | None = None,
    config_path: Path | None = None,
) -> Path:
    """REFUSES an unknown flavour by name, as the site refuses an unknown audience.

    @brief Build Markdown.
    @return Directory.
    """
    from .build import _all_flows, _audience, _commit, _with_role
    from .config import load_wiki_config
    from .tracepages import Trace

    if flavor not in FLAVORS:
        raise ValueError(f"unknown flavour {flavor!r} (known: {', '.join(FLAVORS)})")
    dialect: _Flavor = _GitHub() if flavor == "github" else _Ado()
    config, problems = load_wiki_config(Path(repo_root), config_path)
    if problems:
        raise ValueError("wiki configuration problems: " + "; ".join(problems))
    rules = _audience(config, audience)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    trace = Trace.gather(Path(repo_root), Path(db), config, _commit(Path(repo_root)))
    flows = [
        _flow_page(Path(repo_root), Path(db), _with_role(s, config), dialect, out)
        for s in _all_flows(Path(repo_root), Path(db), config)
    ]
    pages = [("Home", "Home"), ("Requirements", "Requirements"), ("Flows", "Flows")]
    _write(out, "Requirements", _requirements(trace, rules))
    _write(out, "Flows", _flows_index(flows, dialect))
    if trace.impact is not None:
        _write(out, "Change-impact", _impact(trace, rules))
        pages.append(("Change-impact", "Change impact"))
    _write(out, "Home", _home(config.title, trace, len(flows), dialect, pages))
    dialect.order(out, pages + [(page, label) for page, label, _role in flows])
    return out


## @brief Write one page.
## @param out The wiki directory.
## @param page The page name.
## @param text Its Markdown.
## @return None.
## @version 1
## @dg_internal
def _write(out: Path, page: str, text: str) -> None:
    """@brief Write. @return None."""
    (out / f"{page}.md").write_text(text.rstrip() + "\n", encoding="utf-8")


## @brief Home: what the wiki holds, and what only the HTML site has.
## @param title The wiki's title.
## @param trace The trace.
## @param flows How many flow pages.
## @param dialect The host's dialect.
## @param pages (page, label) of the top pages.
## @return Markdown.
## @version 1
## @dg_internal
def _home(title: str, trace: Any, flows: int, dialect: _Flavor, pages: list) -> str:
    """@brief Home. @return Markdown."""
    ev = trace.evidence
    links = " · ".join(dialect.link(p, label) for p, label in pages if p != "Home")
    return "\n".join(
        [
            f"# {title}",
            "",
            f"{len(ev)} requirements, {sum(1 for r in ev if r.tier == 'PASS')} passing; "
            f"{flows} flows. Generated by clew wiki from the repository's index.",
            "",
            links,
            "",
            "The system map, its lenses and the call graphs around each function are drawn by "
            "the HTML site (`clew wiki build`), not by this Markdown wiki.",
        ]
    )


## @brief The requirements, per group, as tables.
## @param trace The trace.
## @param rules The audience rules.
## @return Markdown.
## @version 1
## @dg_internal
def _requirements(trace: Any, rules: Any) -> str:
    """WITHHELD TEXT IS A WITHHELD COLUMN: under `exclude_requirement_text` the title column is
    not drawn at all.

    @brief Requirements.
    @return Markdown.
    """
    from .reqmodal import first
    from .summary import group_of

    show_title = not rules.exclude_requirement_text
    head = [
        "requirement",
        *(["title"] if show_title else []),
        "tier",
        "implemented by",
        "tests",
        "issues",
    ]
    lines = ["# Requirements", ""]
    groups: dict[str, list] = {}
    for row in trace.evidence:
        groups.setdefault(group_of(row.req_id), []).append(row)
    for group, rows in sorted(groups.items()):
        lines += [f"## {group}", "", _row(head), _row(["---"] * len(head))]
        for row in rows:
            title = row.title or str(first(trace.declared.get(row.req_id, {}), "name", "title"))
            issues = ", ".join(
                f"[#{i.id}]({i.url})" for i in (trace.issues or {}).get(row.req_id, [])
            )
            cells = [
                row.req_id,
                *([_cell(title)] if show_title else []),
                row.tier,
                ", ".join(f"`{n}`" for n, _f, _l in row.implementer_sites[:6])
                + (
                    f" (+{len(row.implementer_sites) - 6})"
                    if len(row.implementer_sites) > 6
                    else ""
                ),
                str(len(row.tests)),
                issues,
            ]
            lines.append(_row(cells))
        lines.append("")
    return "\n".join(lines)


## @brief One flow's page: its diagram and its steps.
## @param repo_root The repository.
## @param db The index.
## @param spec The flow.
## @param dialect The host's dialect.
## @param out The wiki directory.
## @return (page, label, role).
## @version 1
## @dg_internal
def _flow_page(
    repo_root: Path, db: Path, spec: Any, dialect: _Flavor, out: Path
) -> tuple[str, str, str]:
    """NAMES ONLY: a step is caller, callee and call site — no call text, no body — so every
    audience can be given the same flow pages.

    @brief Flow page.
    @return Page, label, role.
    """
    from .exports import flow_mermaid
    from .flow import derive_flow
    from .flowpage import page_name

    flow = derive_flow(
        db,
        repo_root,
        spec.entry,
        qualified=spec.qualified,
        depth=spec.depth,
        lanes=spec.lanes,
        stop_at=spec.stop_at,
        file=spec.file,
    )
    page = "Flow-" + page_name(spec).removeprefix("flow-")
    label = (spec.title or spec.entry).replace("`", "")
    lines = [f"# {label}", "", dialect.mermaid(flow_mermaid(flow)), ""]
    lines += [_row(["#", "caller", "callee", "call site"]), _row(["---"] * 4)]
    lines += [
        _row([str(i), f"`{s.caller}`", f"`{s.callee}`", f"{s.site_file or s.file}:{s.line}"])
        for i, s in enumerate(flow.steps, start=1)
    ]
    _write(out, page, "\n".join(lines))
    return page, label, spec.role or "product"


## @brief The flows page: flows grouped by role.
## @param flows (page, label, role) triples.
## @param dialect The host's dialect.
## @return Markdown.
## @version 1
## @dg_internal
def _flows_index(flows: list[tuple[str, str, str]], dialect: _Flavor) -> str:
    """@brief Flows. @return Markdown."""
    lines = ["# Flows", ""]
    for role in ("product", "threads", "tooling", "tests"):
        members = sorted((p, label) for p, label, r in flows if r == role)
        if members:
            lines += [
                f"## {role.capitalize()}",
                "",
                *(f"- {dialect.link(p, label)}" for p, label in members),
                "",
            ]
    return "\n".join(lines)


## @brief The change-impact page.
## @param trace The trace (its impact report).
## @param rules The audience rules.
## @return Markdown.
## @version 1
## @dg_internal
def _impact(trace: Any, rules: Any) -> str:
    """@brief Impact. @return Markdown."""
    lines = ["# Change impact", ""]
    if not trace.impact:
        return "\n".join([*lines, "No requirement was affected by the last change."])
    lines += [_row(["requirement", "functions changed"]), _row(["---", "---"])]
    for entry in trace.impact:
        fns = ", ".join(f"`{f.get('name')}`" for f in entry.get("functions") or [])
        lines.append(_row([str(entry.get("req_id")), fns]))
    return "\n".join(lines)


## @brief One Markdown table row.
## @param cells The cells.
## @return The row.
## @version 1
## @dg_internal
def _row(cells: list[str]) -> str:
    """@brief Row. @return Markdown."""
    return "| " + " | ".join(cells) + " |"


## @brief Repository text safe inside a table cell.
## @param text The text.
## @return The text, pipes and newlines escaped.
## @version 1
## @dg_internal
def _cell(text: str) -> str:
    """@brief Cell. @return Text."""
    return text.replace("|", "\\|").replace("\n", " ")
