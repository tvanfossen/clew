# SPDX-License-Identifier: MIT
"""Pinned sub-catalogs and external rules: traceability across repositories (1.4.0 W8, #67).

Requirements in this repository are often satisfied against another repository's catalog at a
PINNED version. `wiki.catalogs` names each sibling checkout, its pin (a commit or tag) and the
catalog's path inside it. The catalog is read AT THE PIN (`git show <pin>:<path>`), never from the
sibling's working tree, so the trace describes the version this repository depends on.

`check` names two failures:
  * the pin does not resolve to a commit in the sibling;
  * the catalog MOVED SINCE THE PIN — its content at the sibling's HEAD differs from the pin's. The
    pin no longer describes the requirements the sibling now states; someone must re-pin.

Normative rules kept outside any repository (`wiki.rules`, e.g. a contract's R1..R25) map to the
requirements that realise them, so the trace reads rule → requirement → function → test.

Every git call goes through `gitenv.git_argv` — the sibling's own `.git/config` is never trusted.

`declared_catalog` reads THIS repository's own catalog, through the index's resolver.

@brief Read this repository's catalog and pinned sub-catalogs; check their pins.
@version 2
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import CatalogSpec


## @brief One requirement row of a pinned sub-catalog.
## @version 1
@dataclass(frozen=True)
class CatalogRequirement:
    """@brief Catalog name, id, title and the pin it was read at. @version 1"""

    catalog: str
    req_id: str
    title: str
    pin: str


## @brief The requirements of one sub-catalog, read at its pin.
## @param repo_root This repository (the sibling path is relative to it).
## @param spec The sub-catalog.
## @return (rows, problems).
## @version 1
## @req REQ-DDB-WIKI-005
def catalog_requirements(
    repo_root: Path, spec: CatalogSpec
) -> tuple[list[CatalogRequirement], list[str]]:
    """THE FLAT `[{id, title}]` SHAPE or an `{id: {title|name}}` mapping; anything else yields a
    problem rather than a guess.

    @brief Read a catalog at its pin.
    @return Rows and problems.
    """
    import yaml

    sibling = (Path(repo_root) / spec.repo).resolve()
    text = _git(sibling, "show", f"{spec.pin}:{spec.catalog}")
    if text is None:
        return [], [f"catalog {spec.name!r}: {spec.catalog} is not readable at pin {spec.pin}"]
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [], [f"catalog {spec.name!r}: not YAML at pin {spec.pin}: {exc}"]
    rows = [CatalogRequirement(spec.name, req_id, title, spec.pin) for req_id, title in _pairs(doc)]
    if not rows:
        return [], [f"catalog {spec.name!r}: no `id` rows at pin {spec.pin}"]
    return rows, []


## @brief The requirements catalog the index reads, as declared entries by id.
## @param repo_root The repository.
## @return (repo-relative path or "", {id: entry}).
## @version 1
## @req REQ-DDB-WIKI-015
def declared_catalog(repo_root: Path) -> tuple[str, dict[str, dict]]:
    """THE INDEX'S OWN RESOLVER (`resolve_catalog_path`), so the site and the index never read
    different catalogs. Both shapes the index accepts — a flat `[{id, ...}]` list and the
    `{requirements: {ID: {...}}}` mapping — are read; anything else is an empty catalog.

    @brief Read the catalog.
    @return Path and entries.
    """
    import yaml

    from ..requirements import (
        _is_flat_req_list,
        _keyed_req_entries,
        load_guard_config,
        resolve_catalog_columns,
        resolve_catalog_path,
    )

    guard = load_guard_config(repo_root)
    path = resolve_catalog_path(guard, Path(repo_root))
    if path is None or not path.is_file():
        return "", {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    id_col, _title = resolve_catalog_columns(guard)
    entries = data if _is_flat_req_list(data, id_col) else _keyed_req_entries(data)
    rel = path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    return rel, {str(e.get(id_col) or e.get("id")): e for e in entries if isinstance(e, dict)}


## @brief Problems with one sub-catalog's pin.
## @param repo_root This repository.
## @param spec The sub-catalog.
## @return Problems; [] when the pin resolves and the catalog has not moved since.
## @version 1
## @req REQ-DDB-WIKI-005
def pin_problems(repo_root: Path, spec: CatalogSpec) -> list[str]:
    """@brief Check a pin. @return Problems."""
    sibling = (Path(repo_root) / spec.repo).resolve()
    if not sibling.is_dir():
        return [f"catalog {spec.name!r}: sibling checkout {spec.repo} does not exist"]
    if _git(sibling, "rev-parse", "--verify", "--quiet", f"{spec.pin}^{{commit}}") is None:
        return [f"catalog {spec.name!r}: pin {spec.pin} does not resolve in {spec.repo}"]
    pinned = _git(sibling, "show", f"{spec.pin}:{spec.catalog}")
    head = _git(sibling, "show", f"HEAD:{spec.catalog}")
    if pinned is None:
        return [f"catalog {spec.name!r}: {spec.catalog} does not exist at pin {spec.pin}"]
    if head != pinned:
        return [
            f"catalog {spec.name!r}: {spec.catalog} moved since pin {spec.pin} "
            f"(it differs at {spec.repo} HEAD) — re-pin or trace against the pinned rows"
        ]
    return []


## @brief (id, title) pairs from a catalog document.
## @param doc The parsed catalog.
## @return Pairs, in catalog order.
## @version 1
## @dg_internal
def _pairs(doc: object) -> list[tuple[str, str]]:
    """@brief Extract ids. @return Pairs."""
    if isinstance(doc, list):
        return [
            (str(r["id"]), str(r.get("title") or r.get("name") or ""))
            for r in doc
            if isinstance(r, dict) and r.get("id")
        ]
    if isinstance(doc, dict):
        return [
            (str(k), str((v or {}).get("title") or (v or {}).get("name") or ""))
            for k, v in doc.items()
            if isinstance(v, dict) or v is None
        ]
    return []


## @brief Run git in a sibling checkout through the hardened environment.
## @param cwd The checkout.
## @param args Git arguments.
## @return stdout, or None when git failed.
## @version 1
## @dg_internal
def _git(cwd: Path, *args: str) -> str | None:
    """@brief Run git. @return Output or None."""
    from ..gitenv import git_argv

    try:
        out = subprocess.run(
            git_argv(*args), cwd=cwd, capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None
