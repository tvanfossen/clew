# SPDX-License-Identifier: MIT
"""HTML tables and source links for the wiki's pages.

Owner 2026-11-15 ("linkages are left empty in many spots", "some sections are hard to read"):
every tabular page goes through one helper, which

  * DROPS A COLUMN NO ROW FILLS — a column that is empty everywhere is not a linkage the site
    knows, it is a layout fault;
  * marks an EMPTY CELL with a dash (`class="none"`), so "nothing linked" reads as a statement;
  * right-aligns numeric columns and lets the theme keep identifiers on one line.

Cells are HTML the caller built; text from the repository goes through `code` or `text`, which
escape it.

@brief Build HTML tables and source links.
@version 2
"""

from __future__ import annotations

from html import escape

_NONE = '<span class="none">—</span>'


## @brief A table, its all-empty columns dropped and its empty cells dashed.
## @param headers Column headers.
## @param rows Rows of cell HTML ("" is empty).
## @param cls Extra classes for the table.
## @param numeric Headers of right-aligned columns.
## @param keep Headers kept even when empty everywhere.
## @param row_attrs One attribute string per row (e.g. ` data-group="X"`), or None.
## @return HTML.
## v2: every cell names its column (`data-label`), which the narrow-screen card layout prints
## (round 3, P1b).
## v3: `row_attrs` (the requirement list's group filter, P1d).
## @version 3
## @req REQ-DDB-WIKI-012
def table(
    headers: list[str],
    rows: list[list[str]],
    cls: str = "",
    numeric: tuple[str, ...] = (),
    keep: tuple[str, ...] = (),
    row_attrs: list[str] | None = None,
) -> str:
    """@brief Render a table. @return HTML."""
    used = [i for i, h in enumerate(headers) if h in keep or any(r[i] for r in rows)]
    align = {i: ' class="n"' if headers[i] in numeric else "" for i in used}
    label = {i: f' data-label="{escape(headers[i])}"' for i in used}
    head = "".join(f"<th{align[i]}>{escape(headers[i])}</th>" for i in used)
    attrs = row_attrs or [""] * len(rows)
    body = "".join(
        f"<tr{a}>"
        + "".join(f"<td{align[i]}{label[i]}>{r[i] or _NONE}</td>" for i in used)
        + "</tr>"
        for r, a in zip(rows, attrs, strict=True)
    )
    classes = f"clew {cls}".strip()
    return (
        f'<div class="table-wrap"><table class="{classes}"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


## @brief Repository text as inline code.
## @param value The text.
## @return HTML.
## @version 1
## @utility
def code(value: str) -> str:
    """@brief Escape as code. @return HTML."""
    return f"<code>{escape(value)}</code>"


## @brief Repository text, escaped.
## @param value The text.
## @return HTML.
## @version 1
## @utility
def text(value: str) -> str:
    """@brief Escape. @return HTML."""
    return escape(value)


## @brief A tier or status as a themed tag.
## @param value The tier or status.
## @return HTML.
## @version 1
## @utility
def tag(value: str) -> str:
    """@brief Tag. @return HTML."""
    return f'<span class="tier t-{escape(value)}">{escape(value)}</span>'


## @brief A source URL from the link template, or "" when no template is set.
## @param template The template (`{commit}`, `{file}`, `{line}`).
## @param commit The commit.
## @param rel Repo-relative file.
## @param line Line number.
## @return The URL or "".
## @version 1
## @utility
def source_url(template: str, commit: str, rel: str, line: int) -> str:
    """@brief Format. @return URL."""
    return template.format(commit=commit, file=rel, line=line) if template and rel else ""


## @brief A name linked to its source when a URL exists.
## @param name The name.
## @param url The URL, or "".
## @return HTML.
## @version 1
## @utility
def linked(name: str, url: str) -> str:
    """@brief Link. @return HTML."""
    return f'<a href="{escape(url)}">{code(name)}</a>' if url else code(name)


## @brief A flow title (Markdown with inline code spans) as HTML.
## @param title The title.
## @return HTML.
## @version 1
## @utility
def md_title(title: str) -> str:
    """@brief Inline code spans become <code>, everything escaped. @return HTML."""
    parts = escape(title).split("`")
    return "".join(f"<code>{s}</code>" if i % 2 else s for i, s in enumerate(parts))


## @brief Gherkin steps as a list, each keyword marked (W-1 / W-9, owner review 2026-11-22).
## @param lines One step per line, each starting Given / When / Then / And / But.
## @return HTML, or "" for none.
## @version 1
## @utility
def gherkin(lines: tuple[str, ...] | list[str]) -> str:
    """ONE RENDERING for a flow's scenario and a requirement's: declared text, escaped.

    @brief Scenario list.
    @return HTML.
    """
    rows = "".join(
        f'<li><b class="kw">{escape(kw)}</b> {escape(rest)}</li>'
        for kw, _sp, rest in (str(line).partition(" ") for line in lines if str(line).strip())
    )
    return f'<ol class="gherkin" aria-label="Scenario">{rows}</ol>' if rows else ""
