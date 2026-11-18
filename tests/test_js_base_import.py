# SPDX-License-Identifier: MIT
"""A JS/TS base class imported from a package is not the repository's own class (R5-CORE D7; 2.0.0).

FOUND BY THE 2.0.0 CORE AUDIT (agent C, vetted: synth.py:647): a base resolved by BARE TAIL NAME
when exactly one JS/TS class had it, so `class X extends React.Component` linked to the repo's own
lone `Component` class although the heritage names the `react` import. The file's import
bindings now come first: a base whose root name is bound by an import from a PACKAGE specifier
(not `./` or `../`) is external and contributes no base name to resolve.

@brief Tests import-aware base resolution.
@version 1
"""

from __future__ import annotations

import pytest

from clew.tsnode import Parser


def _bases(source: str) -> list[str]:
    """@brief The bases the JS front end records for the file's last class. @return Names."""
    from clew.jsast import _bases as bases_of

    tree = Parser("javascript").parse(source.encode())
    classes = [n for n in tree.root_node.named_children if n.type == "class_declaration"]
    return bases_of(classes[-1])


@pytest.mark.parametrize(
    "source",
    [
        "import React from 'react';\nclass X extends React.Component {}\n",
        "import * as R from 'react';\nclass X extends R.Component {}\n",
        "import { Component } from 'react';\nclass X extends Component {}\n",
        "import { Component as C } from '@scope/ui';\nclass X extends C {}\n",
    ],
)
def test_a_package_import_base_is_external(source: str) -> None:
    """@brief No base name is recorded, so nothing can link to a local class of that name."""
    assert _bases(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "import { Component } from './component';\nclass X extends Component {}\n",
        "import * as ui from '../ui';\nclass X extends ui.Component {}\n",
        "class Component {}\nclass X extends Component {}\n",
    ],
)
def test_a_local_or_relative_base_still_resolves(source: str) -> None:
    """@brief Relative imports and same-file classes keep their base name."""
    assert _bases(source) == ["Component"]
