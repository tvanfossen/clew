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
            definition TEXT, scope TEXT, initializer TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER, line INTEGER,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        INSERT INTO path (rowid, name) VALUES (1, 'include/api.h');
        INSERT INTO memberdef (rowid, name, kind, file_id, bodyfile_id, bodystart, bodyend,
                               line, briefdescription, detaileddescription, static)
        VALUES (5, 'ent_decision_t', 'enumeration', 1, 1, 1, 4, 1,
                '<para>Consumer decision returned from delegation callbacks.</para>',
                '<para>Used by both callbacks.</para>', 0);
        INSERT INTO memberdef (rowid, name, kind, scope, initializer, file_id, line, static)
        VALUES (6, 'ENT_DECISION_ACCEPT', 'enumvalue', 'ent_decision_t', '0', 1, 2, 0),
               (7, 'ENT_DECISION_REJECT', 'enumvalue', 'ent_decision_t', '1', 1, 3, 0);
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


def test_the_enum_lists_the_values_the_index_holds(tmp_path: Path) -> None:
    """The recovered `enumvalue` rows, read back through `scope`. A C enum is a `memberdef`
    and not a `compounddef`, so there is no compound for a `member` link to point at and the
    relation is carried by `scope` — which is why this reads that column rather than the
    member table the class view uses."""
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "ent_decision_t", repo_root=repo)
    assert doss is not None and doss.enumeration is not None
    got = [(e.name, e.value) for e in doss.enumeration.enumerators]
    assert got == [("ENT_DECISION_ACCEPT", "0"), ("ENT_DECISION_REJECT", "1")]


def test_asking_for_a_VALUE_answers_with_the_enum_that_declares_it(tmp_path: Path) -> None:
    """THE REPORTER'S ACTUAL CALL. They asked about four enum symbols they knew existed and
    got a definitive negative on all four; the symbols were VALUES, not types.

    The record's `name` stays the ENUM's, because that is what this record describes —
    renaming it to the queried string would report a symbol under a name it does not have,
    which is the `macro_collision` failure one subject over. `matched_enumerator` is how the
    reply says the query named a value and this is what declares it.
    """
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "ENT_DECISION_ACCEPT", repo_root=repo)
    assert doss is not None and doss.enumeration is not None
    assert doss.enumeration.name == "ent_decision_t", "the record describes the enum"
    assert doss.enumeration.matched_enumerator == "ENT_DECISION_ACCEPT", (
        "the reply must say which value the caller actually asked for"
    )
    assert [e.name for e in doss.enumeration.enumerators] == [
        "ENT_DECISION_ACCEPT",
        "ENT_DECISION_REJECT",
    ]


def test_asking_for_the_enum_itself_reports_no_matched_value(tmp_path: Path) -> None:
    """THE CONTROL. `matched_enumerator` fires only when the query named a value, so a
    consumer can tell the two calls apart — a field populated on every reply says nothing."""
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "ent_decision_t", repo_root=repo)
    assert doss is not None and doss.enumeration is not None
    assert doss.enumeration.matched_enumerator == ""


def test_the_natural_word_enum_reaches_a_C_enum(tmp_path: Path) -> None:
    """gh#27, a regression gh#6's own fix introduced. `_KIND_ALIASES` mapped `enum -> class`,
    correct when the only enum-ish thing with a subject was a `compounddef` row (a C++ scoped
    `enum class`, Rust's `impl EnumName`). A C enum is a `memberdef` with kind
    `'enumeration'`, not a compound, so the alias sent the caller to a subject the name cannot
    resolve as and `_chosen_kind` correctly returned None:

        dossier("ent_decision_t", kind="enum")  ->  None

    `enum` is the word a human types; `enumeration` is doxygen's spelling, learned only by
    reading a `search` row. The natural guess failing SILENTLY is the shape gh#6 was filed
    over in the first place.

    THE ALIAS IS NOW CONDITIONAL ON WHAT THE NAME IS. It offers `class` first — the compound
    reading, which is what the alias was written for and must keep working — and falls to
    `enumeration` when the name is not a compound.
    """
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "ent_decision_t", kind="enum", repo_root=repo)
    assert doss is not None, "the natural word must reach the enum it names"
    assert doss.kind == "enumeration"
    assert doss.enumeration is not None and doss.enumeration.name == "ent_decision_t"


def test_enum_still_prefers_the_compound_when_the_name_is_one(tmp_path: Path) -> None:
    """THE CONTROL THE ALIAS EXISTS FOR. `enum` was mapped to `class` because a `compounddef`
    row with kind='enum' — an enum that owns members — IS a compound. A name that is one must
    still resolve that way, so the alias offers `class` first and only falls through.
    """
    from clew.query.subject import _chosen_kind

    assert _chosen_kind(("class", "enumeration"), "enum") == "class"
    assert _chosen_kind(("enumeration",), "enum") == "enumeration"
    assert _chosen_kind(("class",), "enum") == "class"


def test_enum_on_a_name_that_is_neither_still_refuses(tmp_path: Path) -> None:
    """A KIND IS A FILTER, NOT AN OVERRIDE — the rule `_chosen_kind` records and its tests
    pin. A conditional alias must not become a way to smuggle in a kind the name does not
    resolve to: `enum` on a plain function is still None, not the function relabelled.
    """
    from clew.query.subject import _chosen_kind

    assert _chosen_kind(("function",), "enum") is None
    assert _chosen_kind((), "enum") is None
