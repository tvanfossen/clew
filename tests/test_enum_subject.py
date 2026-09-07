# SPDX-License-Identifier: MIT
"""gh#6 — an enum type is in the index and `dossier` could not describe it.

`dossier("ent_decision_t")` answered `found: false`. The reply was already HONEST
about it — it said the name is in the index as `enumeration`, "a kind `dossier` does
not describe yet", and routed to `search` — so the dangerous half of this report,
a confident false negative, was already gone. What remained is that a whole kind of
symbol had no subject at all.

WHAT THE INDEX ALREADY HOLDS. On entropic, 35 `memberdef` rows with
`kind='enumeration'`, each carrying a brief, a detail AND a body span:

    ent_decision_t   file 71, line 1133, bodystart 1133, bodyend 1136
                     brief: "Consumer decision returned from delegation callbacks."

The body span is what makes this worth a subject rather than a stub: an enum's body
IS its enumerator list, so returning it answers "what are the values" verbatim from
the source, without inventing a layer.

NOT A FUNCTION DOSSIER WITH EMPTY EDGES. An enum has no callers and no callees, and
reporting `callers: []` for it would be a measurement of something never measurable —
the reason `VariableSubject` exists as its own type rather than reusing `Dossier`.

@brief Tests for the enumeration subject kind.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew import query as q


## The smallest index that carries an enum the way doxygen writes one.
_SOURCE = """\
typedef enum {
    ENT_DECISION_ACCEPT = 0,
    ENT_DECISION_REJECT = 1,
} ent_decision_t;
"""


##
# @brief Build an index holding one enumeration row with a body span.
# @param tmp_path Pytest temp dir.
# @return (db path, repo root).
# @version 1
def _index(tmp_path: Path) -> tuple[Path, Path]:
    """@brief Seed a doxygen-shaped index with one enumeration."""
    repo = tmp_path / "repo"
    (repo / "include").mkdir(parents=True)
    (repo / "include" / "api.h").write_text(_SOURCE, encoding="utf-8")
    db = tmp_path / "e.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, type TEXT, argsstring TEXT,
            definition TEXT, scope TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, line INTEGER,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        INSERT INTO path (rowid, name) VALUES (1, 'include/api.h');
        INSERT INTO memberdef (rowid, name, kind, file_id, bodyfile_id, bodystart, bodyend,
                               line, briefdescription, detaileddescription, static)
        VALUES (5, 'ent_decision_t', 'enumeration', 1, 1, 1, 4, 1,
                '<para>Consumer decision returned from delegation callbacks.</para>',
                '<para>Used by both callbacks.</para>', 0);
        """,
    )
    conn.commit()
    conn.close()
    return db, repo


def test_an_enum_type_resolves_to_its_own_subject(tmp_path: Path) -> None:
    """The kind is `enumeration`, which is the string `search` already puts on these rows —
    so the value a consumer reads off a search result passes straight back into `dossier`,
    which is what `search`'s own description promises."""
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "ent_decision_t", repo_root=repo)
    assert doss is not None
    assert doss.kind == "enumeration"
    assert doss.enumeration is not None
    assert doss.enumeration.name == "ent_decision_t"
    assert doss.enumeration.brief == "Consumer decision returned from delegation callbacks."
    assert doss.enumeration.detail == "Used by both callbacks."
    assert doss.enumeration.file == "include/api.h"


def test_the_body_carries_the_enumerators_verbatim(tmp_path: Path) -> None:
    """WHY THIS IS A SUBJECT AND NOT A STUB. doxygen emits no `enumvalue` rows at all —
    zero on entropic — so the individual enumerators are not indexed and cannot be listed
    from the database. They ARE in the body span the enumeration row carries, so returning
    it answers "what are the values" from the source rather than from an invented layer.
    """
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "ent_decision_t", repo_root=repo)
    assert doss is not None and doss.enumeration is not None
    body = doss.enumeration.body
    assert body is not None, "an enum with a body span must return it"
    text = "\n".join(body.lines)
    assert "ENT_DECISION_ACCEPT" in text and "ENT_DECISION_REJECT" in text


def test_an_enum_subject_has_no_caller_fields_at_all(tmp_path: Path) -> None:
    """BY ABSENCE, NOT BY EMPTINESS — the rule `VariableSubject` states. An enum has no
    callers and no callees, so `callers: []` on one would be a measurement of something
    that was never measurable, and this whole session has been spent removing exactly that
    shape.
    """
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "ent_decision_t", repo_root=repo)
    assert doss is not None and doss.enumeration is not None
    assert not hasattr(doss.enumeration, "callers")
    assert not hasattr(doss.enumeration, "callees")
    assert doss.function is None, "an enum must not be answered as a function"


def test_asking_for_the_enumeration_kind_filters_rather_than_relabels(tmp_path: Path) -> None:
    """`kind` is a FILTER, not an override — the rule `_chosen_kind` records. A name that
    is not an enum must return nothing when one is asked for, rather than something else
    wearing the label."""
    db, repo = _index(tmp_path)
    assert q.dossier(db, "ent_decision_t", kind="enumeration", repo_root=repo) is not None
    assert q.dossier(db, "no_such_name", kind="enumeration", repo_root=repo) is None
