# SPDX-License-Identifier: MIT
"""A JS/TS base class imported from a declared dependency is not the repository's own class (R5-CORE D7; 2.0.0).

FOUND BY THE 2.0.0 CORE AUDIT (agent C, vetted: synth.py:647): a base resolved by BARE TAIL NAME
when exactly one JS/TS class had it, so `class X extends React.Component` linked to the repo's own
lone `Component` class although the heritage names the `react` import.

A NON-RELATIVE IMPORT IS NOT NECESSARILY A PACKAGE. A first cut that treated every non-relative
specifier as external was measured on mattermost before it shipped: 27 `compoundref` rows and 82
inherited-member call edges lost, every one into the repo's own `base_data_operator`, imported as
`@database/operator/base_data_operator` — a tsconfig path alias. External is therefore "a package
the repository's package.json declares as a dependency", decided at link time.

@brief Tests import-aware base resolution.
@version 2
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clew.synth import emit_definitions, register_paths

_SCHEMA = Path(__file__).resolve().parent.parent / "clew" / "data" / "doxygen_schema.sql"


def _links(tmp_path: Path, files: dict[str, str], deps: dict | None) -> set[tuple[str, str]]:
    """@brief Build the JS front end over `files`; return (derived, base) links. @return Pairs."""
    root = tmp_path / "repo"
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    if deps is not None:
        (root / "package.json").write_text(json.dumps({"dependencies": deps}))
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    register_paths(db, sorted(files))
    emit_definitions(db, root, None)
    q = (
        "SELECT d.name, b.name FROM compoundref r JOIN compounddef d ON d.rowid = r.derived_rowid "
        "JOIN compounddef b ON b.rowid = r.base_rowid"
    )
    return {
        (d.rsplit("::", 1)[-1], b.rsplit("::", 1)[-1]) for d, b in sqlite3.connect(db).execute(q)
    }


_LOCAL_COMPONENT = {"src/component.js": "export class Component {}\n"}


@pytest.mark.parametrize(
    "source",
    [
        "import React from 'react';\nclass X extends React.Component {}\n",
        "import * as R from 'react';\nclass X extends R.Component {}\n",
        "import { Component } from 'react';\nclass X extends Component {}\n",
        "import { Component as C } from 'react/sub';\nclass X extends C {}\n",
    ],
)
def test_a_dependency_base_does_not_link_to_a_local_class(tmp_path: Path, source: str) -> None:
    """@brief `react` is a declared dependency: X does not inherit the repo's own Component."""
    assert _links(tmp_path, {**_LOCAL_COMPONENT, "src/x.js": source}, {"react": "18"}) == set()


@pytest.mark.parametrize(
    "source",
    [
        "import { Component } from './component';\nclass X extends Component {}\n",
        "import { Component } from '@app/component';\nclass X extends Component {}\n",
        "import React from 'react';\nclass X extends React.Component {}\n",
    ],
)
def test_a_relative_alias_or_undeclared_base_still_links(tmp_path: Path, source: str) -> None:
    """A relative import, a path alias (`@app/...`, not a dependency) and — with no package.json —
    an undecidable package all keep the unique-name link.

    @brief Not a declared dependency: links as before.
    """
    assert _links(
        tmp_path, {**_LOCAL_COMPONENT, "src/x.js": source}, None if "react" in source else {}
    ) == {("X", "Component")}
