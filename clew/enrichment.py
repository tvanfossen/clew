# SPDX-License-Identifier: MIT
"""Optional architecture-topics enrichment from a YAML curriculum file.

Used by `--enrich data/architecture_topics.yaml`. Reads a list of
topic entries with fields topic / title / summary / key_files /
key_concepts / prerequisite_topics / difficulty, and inserts into
the architecture_topics table. Replaces any existing rows.

@brief YAML curriculum enrichment.
@version 1
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from ._common import logger


## @brief Create the architecture_topics table schema (and clear any rows).
## @version 1
## @dg_internal
def _create_topics_table(conn: sqlite3.Connection) -> None:
    """Create the architecture_topics table schema (and clear any rows)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS architecture_topics (
            id INTEGER PRIMARY KEY,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            key_files TEXT NOT NULL,
            key_concepts TEXT NOT NULL,
            prerequisite_topics TEXT,
            difficulty INTEGER DEFAULT 1
        )
        """,
    )
    conn.execute("DELETE FROM architecture_topics")
    conn.commit()


## @brief Insert topic entries into the architecture_topics table.
## @version 1
## @dg_internal
def _insert_topics(conn: sqlite3.Connection, topics: list[dict]) -> None:
    """Insert topic entries into the architecture_topics table."""
    for topic in topics:
        conn.execute(
            """
            INSERT INTO architecture_topics
               (topic, title, summary, key_files, key_concepts,
                prerequisite_topics, difficulty)
               VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic["topic"],
                topic["title"],
                topic["summary"],
                json.dumps(topic.get("key_files", [])),
                json.dumps(topic.get("key_concepts", [])),
                json.dumps(topic.get("prerequisite_topics", [])),
                topic.get("difficulty", 1),
            ),
        )
    conn.commit()


## @brief Populate architecture_topics table from a YAML curriculum file.
## @version 1
## @req REQ-DDB-PIPE-001
def enrich_database(db_path: Path, yaml_path: Path) -> None:
    """Populate architecture_topics table from a YAML curriculum file.

    The YAML file should contain a list of topic entries with fields:
    topic, title, summary, key_files, key_concepts, prerequisite_topics,
    difficulty. Existing rows in architecture_topics are deleted before
    insert so re-running the build idempotently overwrites the table.

    @brief Add architecture_topics table from YAML enrichment file.
    @version 2
    """
    try:
        import yaml
    except ImportError:
        logger.error("PyYAML required for enrichment: pip install pyyaml")
        sys.exit(1)

    topics = yaml.safe_load(yaml_path.read_text())
    if not isinstance(topics, list):
        logger.error("Expected a YAML list in %s", yaml_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    _create_topics_table(conn)
    _insert_topics(conn, topics)
    conn.close()
    logger.info(
        "Enriched database with %d topics from %s",
        len(topics),
        yaml_path,
    )
