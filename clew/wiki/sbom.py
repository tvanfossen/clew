# SPDX-License-Identifier: MIT
"""The SBOM page: the repository's own SBOM rendered, beside its files' licences (#70, P5.8).

Issue #70 and owner Q/A 2026-11-20:

* READ the repository's SBOM — SPDX 2.3 JSON first (ISO/IEC 5962:2021, what the gates template's
  `ci sbom` writes), CycloneDX JSON optional (ECMA-424) — and render it: the package's licence and
  a component table (name, version, licence, kind, source, digest).
* FLAG a component whose licence is NOASSERTION, and one not on the accepted list — the list is
  `wiki.sbom.accepted`, else the gates template's `docs/sbom.toml` `accepted`, else none, and with
  none nothing is called unaccepted (the page says so rather than guessing a policy).
* READ-ONLY: the wiki never writes or edits an SBOM.
* Beside it, the index's own per-file SPDX licence layer (S5): counts by licence, and how many
  indexed files carry no identifier.

@brief Read SPDX / CycloneDX SBOMs and render the SBOM page.
@version 1
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path

NOASSERTION = "NOASSERTION"


## @brief One SBOM component, as the page shows it.
## @version 1
@dataclass(frozen=True)
class Component:
    """@brief Name, version, licence, kind, source, digest (`ALG:value`)."""

    name: str
    version: str
    licence: str
    kind: str
    source: str
    digest: str


## @brief Read one SBOM file, SPDX 2.3 or CycloneDX JSON, by its content.
## @param path The file.
## @return ((package name, package licence), components).
## @version 1
## @req REQ-DDB-WIKI-051
def read_sbom(path: Path) -> tuple[tuple[str, str], list[Component]]:
    """FORMAT BY CONTENT, not by file name: `spdxVersion` is SPDX, `bomFormat: CycloneDX` is
    CycloneDX; anything else raises ValueError naming the file, so a wrong file is a build fault
    the page reports, never a silently empty table.

    @brief Read an SBOM.
    @return Package and components.
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if str(doc.get("spdxVersion", "")).startswith("SPDX-"):
        return _spdx(doc)
    if doc.get("bomFormat") == "CycloneDX":
        return _cyclonedx(doc)
    raise ValueError(f"{path} is neither SPDX JSON nor CycloneDX JSON")


## @brief SPDX 2.3 JSON: the described package, and every other package as a component.
## @param doc The document.
## @return Package and components.
## @version 1
## @utility
def _spdx(doc: dict) -> tuple[tuple[str, str], list[Component]]:
    """@brief SPDX. @return Pair."""
    described = set(doc.get("documentDescribes") or ())
    packages = doc.get("packages") or []
    main = next((p for p in packages if p.get("SPDXID") in described), None)
    comps = [
        Component(
            name=str(p.get("name", "")),
            version=str(p.get("versionInfo", "")),
            licence=str(p.get("licenseConcluded") or p.get("licenseDeclared") or NOASSERTION),
            kind=str(p.get("primaryPackagePurpose", "")).lower(),
            source=_spdx_source(p),
            digest=next(
                (f"{c['algorithm']}:{c['checksumValue']}" for c in p.get("checksums") or ()), ""
            ),
        )
        for p in packages
        if p is not main
    ]
    licence = str(
        (main or {}).get("licenseDeclared") or (main or {}).get("licenseConcluded") or NOASSERTION
    )
    return (str((main or {}).get("name", doc.get("name", ""))), licence), comps


## @brief An SPDX package's source: its download location, unless that is NOASSERTION / NONE.
## @param package The package.
## @return The source, or "".
## @version 1
## @utility
def _spdx_source(package: dict) -> str:
    """@brief Source. @return Text."""
    where = str(package.get("downloadLocation", ""))
    return "" if where in (NOASSERTION, "NONE") else where


## @brief CycloneDX JSON: metadata's component, and the components.
## @param doc The document.
## @return Package and components.
## @version 1
## @utility
def _cyclonedx(doc: dict) -> tuple[tuple[str, str], list[Component]]:
    """@brief CycloneDX. @return Pair."""
    main = (doc.get("metadata") or {}).get("component") or {}
    comps = [
        Component(
            name=str(c.get("name", "")),
            version=str(c.get("version", "")),
            licence=_cdx_licence(c),
            kind=str(c.get("type", "")),
            source=str(c.get("purl", "")),
            digest=next((f"{h['alg']}:{h['content']}" for h in c.get("hashes") or ()), ""),
        )
        for c in doc.get("components") or []
    ]
    return (str(main.get("name", "")), _cdx_licence(main)), comps


## @brief A CycloneDX licence: an expression, else the ids or names joined with AND.
## @param item A component.
## @return The licence, or NOASSERTION.
## @version 1
## @utility
def _cdx_licence(item: dict) -> str:
    """@brief Licence. @return Text."""
    parts = []
    for entry in item.get("licenses") or ():
        if entry.get("expression"):
            return str(entry["expression"])
        lic = entry.get("license") or {}
        if lic.get("id") or lic.get("name"):
            parts.append(str(lic.get("id") or lic.get("name")))
    return " AND ".join(parts) or NOASSERTION


## @brief The SBOM page's HTML.
## @param sboms (file, (package, licence), components) per SBOM read.
## @param accepted The accepted-licence list, or () when none is declared.
## @param file_licences Licence → how many indexed files carry it (S5).
## @param unlicensed How many indexed files carry no identifier.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-051
def sbom_html(sboms: list, accepted: tuple[str, ...], file_licences: dict, unlicensed: int) -> str:
    """@brief SBOMs, then the files' licences. @return HTML."""
    parts = [_policy(accepted)]
    if not sboms:
        parts.append(
            '<p class="none">No SBOM was found: none is declared under <code>wiki.sbom.files</code> '
            "and none is at the repository root (<code>sbom.spdx.json</code>, "
            "<code>bom.cdx.json</code>). The wiki renders an SBOM; it never makes one.</p>"
        )
    for rel, (name, licence), comps in sboms:
        rows = "".join(_row(c, accepted) for c in comps)
        parts.append(
            f'<section class="sbom"><h2><code>{escape(rel)}</code></h2>'
            f"<p>Package <strong>{escape(name)}</strong>, licence <code>{escape(licence)}</code>; "
            f"{len(comps)} components.</p>"
            '<div class="table-wrap"><table class="clew sbom"><thead><tr><th>component</th>'
            "<th>version</th><th>licence</th><th>kind</th><th>source</th><th>digest</th></tr>"
            f"</thead><tbody>{rows}</tbody></table></div></section>"
        )
    parts.append(_files(file_licences, unlicensed))
    return "".join(parts)


## @brief The accepted-licence list, or the sentence for none.
## @param accepted The list.
## @return HTML.
## @version 1
## @utility
def _policy(accepted: tuple[str, ...]) -> str:
    """@brief Policy. @return HTML."""
    if not accepted:
        return (
            '<p class="none">No accepted-licence list is declared (<code>wiki.sbom.accepted</code>, '
            "or <code>accepted</code> in <code>docs/sbom.toml</code>), so no component is called "
            "unaccepted; NOASSERTION is still flagged.</p>"
        )
    return (
        "<p>Accepted licences: " + ", ".join(f"<code>{escape(a)}</code>" for a in accepted) + "</p>"
    )


## @brief One component's row, flagged when its licence is NOASSERTION or not accepted.
## @param comp The component.
## @param accepted The accepted list ("" = none declared).
## @return HTML.
## @version 1
## @utility
def _row(comp: Component, accepted: tuple[str, ...]) -> str:
    """AN EXPRESSION IS ACCEPTED when every licence id in it is (`MIT AND Zlib`); an `OR` choice
    when any branch is. A licence with no policy declared is never called unaccepted.

    @brief Row.
    @return HTML.
    """
    flag = ""
    if comp.licence in (NOASSERTION, "NONE", ""):
        flag = ' <span class="flag noassertion">NOASSERTION</span>'
    elif accepted and not _accepted(comp.licence, set(accepted)):
        flag = ' <span class="flag unaccepted">not accepted</span>'
    cells = [comp.version, comp.licence, comp.kind, comp.source, comp.digest]
    tds = "".join(f"<td>{escape(c)}</td>" for c in cells)
    return f"<tr><td><code>{escape(comp.name)}</code>{flag}</td>{tds}</tr>"


## @brief Whether an SPDX expression is covered by the accepted list.
## @param expression The licence expression.
## @param accepted The accepted ids.
## @return True when accepted.
## @version 1
## @utility
def _accepted(expression: str, accepted: set[str]) -> bool:
    """@brief Every AND term, any OR branch. @return Accepted."""
    text = expression.replace("(", " ").replace(")", " ")
    return any(
        all(term.strip() in accepted for term in branch.split(" AND ") if term.strip())
        for branch in text.split(" OR ")
    )


## @brief The repository's files' licences, from the index (S5).
## @param file_licences Licence → count.
## @param unlicensed Indexed files with no identifier.
## @return HTML.
## @version 1
## @utility
def _files(file_licences: dict, unlicensed: int) -> str:
    """@brief File licences. @return HTML."""
    rows = "".join(
        f'<tr><td><code>{escape(lic)}</code></td><td class="n">{n}</td></tr>'
        for lic, n in sorted(file_licences.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    table = (
        f'<table class="clew"><thead><tr><th>licence</th><th class="n">files</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
        if rows
        else '<p class="none">No indexed file carries an SPDX identifier.</p>'
    )
    return (
        '<section class="file-licences"><h2>This repository\'s files</h2>'
        "<p>The SPDX identifier each indexed file declares (<code>SPDX-License-Identifier</code>), "
        "from the index.</p>"
        f"{table}<p>{unlicensed} indexed files carry no SPDX identifier.</p></section>"
    )


## @brief Write the SBOM page from the repository's SBOMs and the index's file licences.
## @param repo_root The repository.
## @param db The index.
## @param config The section (`sbom_files`, `sbom_accepted`).
## @param source The Sphinx source directory.
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-051
def sbom_page(repo_root: Path, db: Path, config, source: Path) -> str:  # noqa: ANN001
    """AN SBOM THAT WILL NOT READ IS SAID, by file and reason, not dropped: the page lists it under
    the table rather than failing the whole site.

    @brief Write sbom.md.
    @return Page name.
    """
    root = Path(repo_root)
    sboms, refused = [], []
    for path in sorted({p for g in config.sbom_files for p in root.glob(g) if p.is_file()}):
        rel = path.relative_to(root).as_posix()
        try:
            sboms.append((rel, *read_sbom(path)))
        except (OSError, ValueError) as exc:
            refused.append(f"<li><code>{escape(rel)}</code>: {escape(str(exc))}</li>")
    accepted = config.sbom_accepted or _toml_accepted(root / "docs" / "sbom.toml")
    counts, unlicensed = _file_licences(db)
    html = sbom_html(sboms, accepted, counts, unlicensed)
    if refused:
        html += f'<p class="bad">Not read:</p><ul>{"".join(refused)}</ul>'
    lines = [
        "# SBOM",
        "",
        "The software bill of materials this repository carries, rendered as it is (the wiki never "
        "writes one), and the licence each of its own files declares.",
        "",
        "```{raw} html",
        html,
        "```",
        "",
    ]
    (Path(source) / "sbom.md").write_text("\n".join(lines), encoding="utf-8")
    return "sbom"


## @brief The gates template's accepted-licence list, from `docs/sbom.toml`.
## @param path The file.
## @return The list, or () when absent or unreadable.
## @version 1
## @utility
def _toml_accepted(path: Path) -> tuple[str, ...]:
    """@brief Read `accepted`. @return Ids."""
    from ..tomlcompat import toml_module

    toml = toml_module()
    if toml is None or not path.is_file():
        return ()
    try:
        accepted = toml.loads(path.read_text(encoding="utf-8")).get("accepted") or ()
    except (OSError, ValueError):
        return ()
    return tuple(str(a) for a in accepted)


## @brief Licence counts over the index's files, and how many indexed files carry none.
## @param db The index.
## @return ({licence: files}, files with no identifier).
## @version 1
## @utility
def _file_licences(db: Path) -> tuple[dict[str, int], int]:
    """A MISSING LAYER IS NOT ZERO: an index without `file_licenses` reports no counts and no
    unlicensed total rather than claiming every file carries none.

    @brief Count licences.
    @return Counts.
    """
    from ..query._common import connect, table_exists

    with connect(db) as conn:
        if not table_exists(conn, "file_licenses"):
            return {}, 0
        counts = dict(conn.execute("SELECT license, COUNT(*) FROM file_licenses GROUP BY license"))
        files = conn.execute(
            "SELECT COUNT(*) FROM path p WHERE p.type = 1 AND p.found = 1 AND p.name NOT IN "
            "(SELECT file_path FROM file_licenses)"
        ).fetchone()[0]
    return {str(k): int(v) for k, v in counts.items()}, int(files)
