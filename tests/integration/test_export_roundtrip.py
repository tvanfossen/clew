# SPDX-License-Identifier: MIT
"""A statement survives EXPORT -> DECLARE -> REBUILD, measured on the second index's records.

WHY THE ROUND TRIP IS THE TEST AND NOT THE FILE'S TEXT. `clew export` could emit a
perfectly plausible YAML document that `--declare` then reads as something else — a one-element
list flattened to a scalar, a mapping key renamed, a path made absolute — and every assertion about
the document's contents would pass. The only claim worth making is that a repo can commit what it
exported and get the same index back, so the assertions here are on the SECOND build's recorded
statements, reached through the same helpers a replay uses.

WHAT IT WOULD MISS IF IT ONLY EXPORTED, and why the fixture states a manifest rather than a bare
macro list: `predefined` is a list and reaches `build_meta` through `.explicit`, while a manifest
reaches it as a canonical document. Those are two different stored shapes and two different
readers, so a test exercising one proves nothing about the other. Both are stated here.

THE EMPTY CASE IS ASSERTED TOO. An index that recorded nothing must export a document that states
nothing — not a plausible one assembled from the built-in defaults, which would freeze those
defaults into the target and shadow every later improvement to them.

@brief Integration control for the export/declare round trip.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import build_index
from clew.export_command import render, stated_declaration
from clew.mcp_server.state import _options_meta
from clew.tiers import stated_options

pytestmark = pytest.mark.integration

## A macro the fixture gates on, so a stated `predefined` has an observable consequence beyond its
## own record — the same reason the manifest-replay controls count edge rows rather than metadata.
GATED_MACRO = "ROUNDTRIP_FEATURE_ON"

SOURCE = f"""/** @file
 *  @brief Export round-trip fixture.
 */

#ifdef {GATED_MACRO}
/** @brief Present only when the macro is declared.
 *  @version 1
 */
void roundtrip_gated(void) {{ }}
#endif

/** @brief Always present.
 *  @version 1
 */
void roundtrip_plain(void) {{ }}
"""

DOXYFILE = (
    "PROJECT_NAME     = export_roundtrip\n"
    "INPUT            = src\n"
    "RECURSIVE        = YES\n"
    "GENERATE_HTML    = NO\n"
    "GENERATE_LATEX   = NO\n"
    "EXTRACT_STATIC   = YES\n"
    "QUIET            = YES\n"
)

## A manifest no built-in pattern claims, so its presence in the second index can only have come
## from the exported document.
MANIFEST: dict[str, object] = {
    "writers": [{"name_prefix": "Roundtrip_Set_"}],
    "readers": [{"name_prefix": "Roundtrip_Get_"}],
}


## @brief Write the throwaway C target.
## @param root Directory to populate.
## @return The Doxyfile path.
## @version 1
def _target(root: Path) -> Path:
    """@brief Create the fixture repo.
    @return Doxyfile path.
    @version 1
    """
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "rt.c").write_text(SOURCE, encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(DOXYFILE, encoding="utf-8")
    return doxyfile


def test_an_index_with_no_statement_exports_a_document_that_states_nothing(tmp_path: Path) -> None:
    """THE FLOOR, and it is a real risk rather than a formality. The obvious implementation of an
    export walks the EFFECTIVE configuration — tier 1 over tier 2 over the built-in floor — which
    would write a file asserting the team declared every default. Committing that freezes the
    defaults into the repo, so a later improvement to one is shadowed by a value nobody remembers
    writing, and a tier-5 default becomes indistinguishable from a deliberate decision.

    @brief Nothing stated exports nothing.
    @version 1
    """
    root = tmp_path / "bare"
    doxyfile = _target(root)
    db = tmp_path / "bare.db"
    build_index(output=db, repo_root=root, doxyfile=doxyfile)

    assert stated_declaration(db) == {}, (
        "an index that recorded no statement must export none — anything here is a default being "
        "passed off as a declaration"
    )
    text = render({}, db)
    assert "recorded NO tier-1 statements" in text, (
        "and it must SAY so: a zero-byte file reads as a failed command rather than a result"
    )


def test_a_stated_configuration_survives_export_declare_rebuild(tmp_path: Path) -> None:
    """THREE BUILDS, TWO SHAPES, ASSERTED ON THE THIRD BUILD'S RECORDS.

      1. state a `predefined` LIST and a `shared_key_patterns` DOCUMENT -> both recorded
      2. export -> a YAML file
      3. a FRESH index built with `--declare` that file -> the same statements recorded

    Build 3 uses a DIFFERENT output path deliberately. The replay mechanism (gh#366) reads the
    record out of the database being replaced, so building over the same file would let the REPLAY
    supply the statements and the export could be empty while this test passed. A fresh path has no
    record to replay from, so the only possible source is the exported document.

    @brief The exported document reproduces the statements.
    @version 1
    """
    from clew.declaration import SECTION_SHARED_KEY

    root = tmp_path / "target"
    doxyfile = _target(root)
    first = tmp_path / "first.db"
    build_index(
        output=first,
        repo_root=root,
        doxyfile=doxyfile,
        options={"predefined": [GATED_MACRO], SECTION_SHARED_KEY: MANIFEST},
    )
    stated_first = stated_options(_options_meta(first))
    assert "predefined" in stated_first and SECTION_SHARED_KEY in stated_first, (
        f"the fixture must record BOTH shapes or the round trip proves half of it: {stated_first}"
    )

    exported = stated_declaration(first)
    assert exported.get("predefined") == [GATED_MACRO], (
        f"the list shape must survive as a list, not a scalar: {exported}"
    )
    assert exported.get(SECTION_SHARED_KEY) == MANIFEST, (
        f"the document shape must survive intact: {exported}"
    )

    declaration = tmp_path / "exported.yaml"
    declaration.write_text(render(exported, first), encoding="utf-8")

    ## A FRESH OUTPUT PATH: no record to replay, so the document is the only possible source.
    second = tmp_path / "second.db"
    build_index(output=second, repo_root=root, doxyfile=doxyfile, declare=str(declaration))

    stated_second = stated_options(_options_meta(second))
    assert set(stated_second) == set(stated_first), (
        f"the round trip lost or gained a statement: {stated_second} vs {stated_first}"
    )
    assert stated_declaration(second) == exported, (
        "and the re-exported declaration must equal the first, or the format is not stable under "
        "its own round trip"
    )
