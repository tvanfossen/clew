# SPDX-License-Identifier: MIT
"""Tests for clew.enrichment (the optional `--enrich` curriculum path).

`enrich_database` was shipped and CLI-wired (`--enrich`) but had zero coverage:
no test exercised the YAML→architecture_topics population. These tests pin its
contract — round-trip fidelity, JSON-encoding of the list fields, optional-field
defaults, and the idempotent replace-on-rerun behaviour its docstring promises.

`enrich_database` creates its own `architecture_topics` table, so a bare sqlite
db is a sufficient fixture — no full pipeline build required.

@brief Tests for clew.enrichment.
@version 1
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clew.enrichment import enrich_database

_CURRICULUM = """\
- topic: event_bus
  title: The Event Bus
  summary: Function-pointer subscribe/dispatch.
  key_files: [src/event_bus/event_bus.c]
  key_concepts: [callback, dispatch]
  prerequisite_topics: []
  difficulty: 2
- topic: dataflow
  title: Shared-key Dataflow
  summary: Writers and readers meet on a key, never on a call.
  key_files: [src/dispatch/dm_event_dispatch.c, gen/ingot/dm.c]
  key_concepts: [shared_key, inference]
  prerequisite_topics: [event_bus]
  difficulty: 3
"""


## @brief Write a curriculum YAML and enrich a fresh db from it.
## @param tmp_path Pytest temp dir.
## @param text Curriculum YAML text.
## @return Path to the enriched database.
## @version 1
def _enrich(tmp_path: Path, text: str) -> Path:
    """Create a bare db + curriculum file and run enrich_database.

    @brief Enrich a fresh db from curriculum text.
    @return The enriched db path.
    @version 1
    """
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()  # bare db — enrich_database makes its table
    yaml_path = tmp_path / "topics.yaml"
    yaml_path.write_text(text, encoding="utf-8")
    enrich_database(db, yaml_path)
    return db


## @brief A curriculum round-trips into architecture_topics with list fields JSON-encoded.
## @version 1
def test_enrich_populates_topics(tmp_path: Path) -> None:
    """Each YAML entry becomes one row; scalar fields land verbatim and the
    list fields (key_files / key_concepts / prerequisite_topics) are stored as
    JSON that decodes back to the original lists.

    @brief Curriculum round-trips into the table.
    @version 1
    """
    db = _enrich(tmp_path, _CURRICULUM)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT topic, title, summary, key_files, key_concepts, "
        "prerequisite_topics, difficulty FROM architecture_topics ORDER BY topic"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    dataflow, event_bus = rows  # 'dataflow' < 'event_bus'
    assert event_bus[0] == "event_bus"
    assert event_bus[1] == "The Event Bus"
    assert json.loads(event_bus[3]) == ["src/event_bus/event_bus.c"]
    assert json.loads(event_bus[4]) == ["callback", "dispatch"]
    assert event_bus[6] == 2
    assert dataflow[0] == "dataflow"
    assert json.loads(dataflow[5]) == ["event_bus"]  # prerequisite_topics
    assert dataflow[6] == 3


## @brief Missing optional fields fall back to empty lists / difficulty 1.
## @version 1
def test_enrich_optional_field_defaults(tmp_path: Path) -> None:
    """A minimal entry (only the required scalar fields) inserts cleanly: the
    absent list fields default to `[]` and difficulty to 1.

    @brief Optional fields get sane defaults.
    @version 1
    """
    minimal = "- topic: t\n  title: T\n  summary: S\n"
    db = _enrich(tmp_path, minimal)
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT key_files, key_concepts, prerequisite_topics, difficulty FROM architecture_topics"
    ).fetchone()
    conn.close()
    assert json.loads(row[0]) == []
    assert json.loads(row[1]) == []
    assert json.loads(row[2]) == []
    assert row[3] == 1


## @brief Re-running enrichment replaces rows rather than accumulating them.
## @version 1
def test_enrich_is_idempotent(tmp_path: Path) -> None:
    """The docstring promises re-running the build idempotently overwrites the
    table (DELETE before insert). A second enrich with fewer topics must leave
    exactly those topics, not the union.

    @brief Re-enrich replaces, never accumulates.
    @version 1
    """
    db = _enrich(tmp_path, _CURRICULUM)  # 2 topics
    yaml_path = tmp_path / "topics.yaml"
    yaml_path.write_text("- topic: only\n  title: Only\n  summary: S\n", encoding="utf-8")
    enrich_database(db, yaml_path)  # re-run with 1 topic

    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT topic FROM architecture_topics").fetchall()
    conn.close()
    assert rows == [("only",)]


## @brief A YAML file that isn't a list is rejected (not silently accepted).
## @version 1
def test_enrich_rejects_non_list_yaml(tmp_path: Path) -> None:
    """The contract requires a top-level YAML list; a mapping (or any non-list)
    must fail loudly via `sys.exit(1)` rather than silently produce an empty or
    malformed table.

    @brief Non-list curriculum YAML exits non-zero.
    @version 1
    """
    db = tmp_path / "clew.db"
    sqlite3.connect(str(db)).close()
    yaml_path = tmp_path / "topics.yaml"
    yaml_path.write_text("topic: not_a_list\ntitle: T\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        enrich_database(db, yaml_path)
