# SPDX-License-Identifier: MIT
"""Version-keyed sites and the diff between two of them (1.4.0 W11, #67's fifth consumer).

A contract is versioned, so a site per release tag beats one rolling site. A versioned build
(`clew wiki build --version KEY`) writes `<out>/<KEY>/html` and a SNAPSHOT of what it traced,
`<out>/<KEY>/site.json`: the requirement tiers and the external node addresses (the key space).
`<out>/versions.json` lists every recorded key in the order recorded, and `<out>/index.html` links
each — a plain, self-contained page.

`diff_versions(out, A, B)` compares two snapshots and writes `<out>/diff-A-B.html`:
  * nodes added / removed (the key space);
  * requirements added / removed;
  * requirement tier changes, `{id, from, to}`.

A diff is computed from snapshots, never by rebuilding an old tag: the site recorded what it
traced when it was built, which is the claim a reader of that version saw.

@brief Record version-keyed sites and diff two of them.
@version 1
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

## A version key becomes a directory name: no separators, no leading dot.
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}"
    "table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:.25rem .5rem}"
    ".add{color:#176f2c}.rm{color:#a1261b}"
)


## @brief A version key, refused when it cannot be a directory name.
## @param key The key.
## @return The key.
## @version 1
## @req REQ-DDB-WIKI-007
def valid_key(key: str) -> str:
    """@brief Validate a key. @return Key."""
    if not _KEY.match(key or ""):
        raise ValueError(f"version key {key!r} is not usable as a directory name")
    return key


## @brief Record one versioned build: its snapshot, the version list and the index page.
## @param out The versioned output root.
## @param key The version key.
## @param snapshot What the build traced.
## @param title The site title.
## @return The snapshot path.
## @version 1
## @req REQ-DDB-WIKI-007
def record_version(out: Path, key: str, snapshot: dict[str, Any], title: str) -> Path:
    """REBUILDING A KEY REPLACES ITS ENTRY in place; a new key is appended.

    @brief Record a version.
    @return Snapshot path.
    """
    out = Path(out)
    path = out / valid_key(key) / "site.json"
    path.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    listing = _versions(out)
    entry = {"key": key, "commit": snapshot.get("commit", "")}
    keys = [v["key"] for v in listing]
    if key in keys:
        listing[keys.index(key)] = entry
    else:
        listing.append(entry)
    (out / "versions.json").write_text(json.dumps(listing, indent=1) + "\n", encoding="utf-8")
    rows = "".join(
        f'<li><a href="{html.escape(v["key"])}/html/index.html">{html.escape(v["key"])}</a>'
        f" <code>{html.escape(v['commit'][:12])}</code></li>"
        for v in listing
    )
    _page(out / "index.html", f"{title} — versions", f"<ul>{rows}</ul>")
    return path


## @brief Compare two recorded versions and write the diff page.
## @param out The versioned output root.
## @param old The earlier key.
## @param new The later key.
## @return The diff as plain data.
## @version 1
## @req REQ-DDB-WIKI-007
def diff_versions(out: Path, old: str, new: str) -> dict[str, Any]:
    """@brief Diff two snapshots. @return Diff."""
    out = Path(out)
    a, b = _snapshot(out, old), _snapshot(out, new)
    ra, rb = a.get("requirements", {}), b.get("requirements", {})
    na, nb = set(a.get("nodes", [])), set(b.get("nodes", []))
    diff = {
        "from": old,
        "to": new,
        "nodes_added": sorted(nb - na),
        "nodes_removed": sorted(na - nb),
        "requirements_added": sorted(set(rb) - set(ra)),
        "requirements_removed": sorted(set(ra) - set(rb)),
        "requirements_changed": [
            {"id": i, "from": ra[i], "to": rb[i]}
            for i in sorted(set(ra) & set(rb))
            if ra[i] != rb[i]
        ],
    }
    _page(out / f"diff-{old}-{new}.html", f"Changes {old} → {new}", _diff_body(diff))
    return diff


## @brief The HTML body of a diff page.
## @param diff The diff.
## @return HTML.
## @version 1
## @dg_internal
def _diff_body(diff: dict[str, Any]) -> str:
    """@brief Render. @return HTML."""
    e = html.escape

    def items(key: str, cls: str) -> str:
        rows = "".join(f'<li class="{cls}"><code>{e(x)}</code></li>' for x in diff[key])
        return f"<h2>{e(key.replace('_', ' '))}</h2><ul>{rows or '<li>none</li>'}</ul>"

    changed = "".join(
        f"<tr><td>{e(c['id'])}</td><td>{e(c['from'])}</td><td>{e(c['to'])}</td></tr>"
        for c in diff["requirements_changed"]
    )
    return (
        items("nodes_added", "add")
        + items("nodes_removed", "rm")
        + items("requirements_added", "add")
        + items("requirements_removed", "rm")
        + "<h2>requirement tier changes</h2><table><tr><th>requirement</th><th>from</th>"
        + f"<th>to</th></tr>{changed or '<tr><td colspan=3>none</td></tr>'}</table>"
    )


## @brief Write a self-contained HTML page.
## @param path The file.
## @param title The page title.
## @param body The body HTML.
## @return None.
## @version 1
## @dg_internal
def _page(path: Path, title: str, body: str) -> None:
    """@brief Write a page. @return None."""
    t = html.escape(title)
    path.write_text(
        f'<!doctype html><html><head><meta charset="utf-8"><title>{t}</title>'
        f"<style>{_STYLE}</style></head><body><h1>{t}</h1>{body}</body></html>\n",
        encoding="utf-8",
    )


## @brief The recorded version list.
## @param out The versioned output root.
## @return Entries in recorded order.
## @version 1
## @dg_internal
def _versions(out: Path) -> list[dict[str, str]]:
    """@brief Read versions.json. @return Entries."""
    path = out / "versions.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


## @brief One version's snapshot, refused when it was never recorded.
## @param out The versioned output root.
## @param key The key.
## @return The snapshot.
## @version 1
## @dg_internal
def _snapshot(out: Path, key: str) -> dict[str, Any]:
    """@brief Read a snapshot. @return Data."""
    path = out / valid_key(key) / "site.json"
    if not path.is_file():
        raise ValueError(f"version {key!r} has no recorded site under {out}")
    return json.loads(path.read_text(encoding="utf-8"))
