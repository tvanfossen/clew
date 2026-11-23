# SPDX-License-Identifier: MIT
"""Architecture decision records (round 3, P3c).

A repository's ADRs (`docs/adr/*.md` and the other usual homes, or `wiki.adrs`) are read for
their number, title, status and date — in the shapes ADRs are actually written: Nygard's
`## Status` section, an inline `Status:` line, MADR's YAML front matter — and for the
requirement ids they name. The site lists them on a Decisions page and each requirement's modal
names the decisions that mention it.

@brief Read ADRs and write the Decisions page.
@version 1
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

_NUMBER = re.compile(r"^(\d+)")
_TITLE = re.compile(r"^#\s+(?:(\d+)\.\s*)?(.+?)\s*$", re.M)
_INLINE = re.compile(r"^(Status|Date)\s*:\s*(.+?)\s*$", re.M | re.I)
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


## @brief One decision record.
## @version 1
@dataclass(frozen=True)
class Decision:
    """@brief File, number, title, status, date, named requirements. @version 1"""

    file: str
    number: str
    title: str
    status: str
    date: str
    requirements: tuple[str, ...] = ()

    ## @brief The decision's page, relative to the site root.
    ## @return The href.
    ## @version 1
    ## @req REQ-DDB-WIKI-031
    @property
    def href(self) -> str:
        """@brief Href. @return Path."""
        return f"prose/{Path(self.file).with_suffix('')}.html"


## @brief Parse one ADR.
## @param rel Its repo-relative path.
## @param text Its content.
## @param req_ids Requirement ids to look for (whole ids only).
## @return The decision.
## @version 1
## @req REQ-DDB-WIKI-031
def parse_adr(rel: str, text: str, req_ids: tuple[str, ...] = ()) -> Decision:
    """FRONT MATTER, THEN AN INLINE LINE, THEN A `## Status` SECTION: the first that says it wins.
    The number is the heading's (`# 3. Title`) or the file name's leading digits.

    @brief Parse.
    @return Decision.
    """
    front = _front_matter(text)
    body = _FRONT.sub("", text, count=1)
    heading = _TITLE.search(body)
    inline = {k.lower(): v for k, v in _INLINE.findall(body)}
    number = (heading.group(1) if heading and heading.group(1) else "") or _file_number(rel)
    return Decision(
        rel,
        number.lstrip("0") or number,
        heading.group(2) if heading else Path(rel).stem,
        front.get("status") or inline.get("status") or _section(body, "Status"),
        front.get("date") or inline.get("date") or "",
        tuple(r for r in req_ids if re.search(rf"(?<![\w-]){re.escape(r)}(?![\w])", text)),
    )


## @brief Every ADR under the configured globs.
## @param repo_root The repository.
## @param globs ADR globs.
## @param req_ids Requirement ids to look for.
## @return Decisions, by file.
## @version 1
## @req REQ-DDB-WIKI-031
def find_decisions(
    repo_root: Path, globs: tuple[str, ...], req_ids: tuple[str, ...]
) -> list[Decision]:
    """@brief Find ADRs. @return Decisions."""
    root = Path(repo_root)
    files = sorted({p for g in globs for p in root.glob(g) if p.is_file()})
    return [
        parse_adr(
            p.relative_to(root).as_posix(), p.read_text(encoding="utf-8", errors="replace"), req_ids
        )
        for p in files
    ]


## @brief Write the Decisions page.
## @param decisions The decisions.
## @param source The Sphinx source directory.
## @return The page name, or "" with no decision.
## @version 1
## @req REQ-DDB-WIKI-031
def decisions_page(decisions: list[Decision], source: Path) -> str:
    """@brief Write decisions.md. @return Page name."""
    from .htmltable import table

    if not decisions:
        return ""
    rows = [
        [
            escape(d.number),
            f'<a href="{escape(d.href)}">{escape(d.title)}</a>',
            escape(d.status),
            escape(d.date),
            " ".join(
                f'<a class="req-badge" href="requirements.html#{escape(r)}">{escape(r)}</a>'
                for r in d.requirements
            ),
        ]
        for d in decisions
    ]
    body = table(
        ["#", "decision", "status", "date", "requirements"],
        rows,
        numeric=("#",),
        keep=("decision",),
    )
    pages = [str(Path("prose") / Path(d.file).with_suffix("")) for d in decisions]
    lines = [
        "# Decisions",
        "",
        "The repository's architecture decision records: what was decided, its status, and the "
        "requirements each names.",
        "",
        "```{raw} html",
        body,
        "```",
        "",
        "```{toctree}",
        ":hidden:",
        "",
        *pages,
        "```",
        "",
    ]
    (Path(source) / "decisions.md").write_text("\n".join(lines), encoding="utf-8")
    return "decisions"


## @brief A document's kind: declared, else agent-facing by name, else "".
## @param rel Its repo-relative path.
## @param declared (glob, kind) pairs.
## @return The kind.
## @version 1
## @req REQ-DDB-WIKI-031
def doc_kind(rel: str, declared: tuple[tuple[str, str], ...]) -> str:
    """@brief Kind. @return Kind or ""."""
    for glob, kind in declared:
        if fnmatch.fnmatch(rel, glob):
            return kind
    return "agents" if Path(rel).name in _AGENT_DOCS else ""


## Documents written for agents, kept apart from the human docs.
_AGENT_DOCS = ("AGENTS.md", "CLAUDE.md", "SKILLS.md", "GEMINI.md", "llms.txt")


## @brief MADR-style YAML front matter, as a lower-cased mapping.
## @param text The document.
## @return Keys to strings ({} without front matter).
## @version 1
## @utility
def _front_matter(text: str) -> dict[str, str]:
    """@brief Front matter. @return Mapping."""
    import yaml

    found = _FRONT.match(text)
    if not found:
        return {}
    try:
        data = yaml.safe_load(found.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return {str(k).lower(): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


## @brief The first non-empty line under a `## <name>` heading.
## @param body The document.
## @param name The section.
## @return The line, or "".
## @version 1
## @utility
def _section(body: str, name: str) -> str:
    """@brief Section line. @return Text."""
    found = re.search(rf"^#+\s*{name}\s*\n+\s*(\S.*?)\s*$", body, re.M | re.I)
    return found.group(1) if found else ""


## @brief The leading digits of a file name.
## @param rel The path.
## @return Digits, or "".
## @version 1
## @utility
def _file_number(rel: str) -> str:
    """@brief Number. @return Digits."""
    found = _NUMBER.match(Path(rel).name)
    return found.group(1) if found else ""
