# SPDX-License-Identifier: MIT
"""Check the export API answers what the MCP tools answer, on real indexes.

`tests/test_export.py` proves parity on the synthetic fixture over EVERY name it holds. This runs
the same comparison against real built indexes — the acceptance run databases, which are not in
the repository and cannot run in CI — so the claim "export == MCP minus the boundary" is measured
on C, C++, Python and TypeScript, not only asserted on a fixture.

    .venv/bin/python scripts/export_parity.py <clew.db> <repo root> [--sample N]

A deterministic sample of N distinct names (every k-th, sorted) is compared, plus every search
corpus for a fixed set of texts. Exit 0 when every comparison agrees; 1 with the mismatches named.

@brief Export/MCP parity over a real index.
@version 1
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

from clew import query as q
from clew.mcp_server import tools_query
from clew.mcp_server.tools_query import CORPORA, QueryTools

## Server facts the MCP boundary stamps; not part of the answer.
_BOUNDARY = ("target", "staleness", "sub_index", "not_searched")
## Texts each corpus is searched with.
_TEXTS = ("", "lock", "init", "error", "no_such_token_xyz")


##
# @brief Drop boundary stamps and the export's version stamp.
# @param reply A reply.
# @return The answer part.
# @version 1
def _answer(reply: dict[str, Any]) -> dict[str, Any]:
    """@brief Strip stamps. @return The answer."""
    out = {k: v for k, v in reply.items() if k not in _BOUNDARY and k != "wire_version"}
    if isinstance(out.get("results"), list):
        out["results"] = [
            {k: v for k, v in e.items() if k not in _BOUNDARY} if isinstance(e, dict) else e
            for e in out["results"]
        ]
    return out


##
# @brief Every k-th distinct indexed name, to N.
# @param db The index.
# @param n Sample size.
# @return The names.
# @version 1
def _sample(db: Path, n: int) -> list[str]:
    """@brief Deterministic name sample. @return Names."""
    with sqlite3.connect(db) as conn:
        names = sorted({r[0] for r in conn.execute("SELECT DISTINCT name FROM memberdef") if r[0]})
    step = max(1, len(names) // n)
    return names[::step][:n]


##
# @brief Compare one subject's dossier, modulo a miss's routing sentence.
# @param tools The unbudgeted MCP tool set.
# @param db The index.
# @param repo The working tree.
# @param name The subject.
# @return True when they agree.
# @version 1
def _dossier_agrees(tools: QueryTools, db: Path, repo: Path, name: str) -> bool:
    """@brief One dossier comparison. @return Agreement."""
    mcp = _answer(tools.dossier(name, max_neighbors=10**6))
    exp = _answer(q.export_dossier(db, name, repo_root=repo, max_neighbors=10**6))
    if mcp.get("found") is False:
        tail = exp.get("note", "").split("malformed call.", 1)[-1]
        mcp.pop("note", ""), exp.pop("note", "")
        return mcp == exp and bool(tail)
    return mcp == exp


##
# @brief Run every comparison and report.
# @return Process exit code.
# @version 1
def main() -> int:
    """@brief Entry point. @return 0 when every comparison agrees, else 1."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", type=Path)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--sample", type=int, default=400)
    args = parser.parse_args()
    tools_query.RESPONSE_BUDGET_BYTES = 10**9
    tools = QueryTools(lambda: args.db, lambda: args.repo)
    names = _sample(args.db, args.sample)
    bad = [n for n in names if not _dossier_agrees(tools, args.db, args.repo, n)]
    for corpus in CORPORA:
        for text in _TEXTS:
            mcp = _answer(tools.search(text, corpus=corpus))
            exp = _answer(q.export_search(args.db, text, corpus=corpus, repo_root=args.repo))
            if mcp != exp:
                bad.append(f"search:{corpus}:{text!r}")
    total = len(names) + len(CORPORA) * len(_TEXTS)
    print(f"{args.db}: {total - len(bad)}/{total} agree")
    for item in bad:
        print(f"  MISMATCH {item}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
