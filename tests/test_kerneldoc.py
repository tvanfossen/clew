# SPDX-License-Identifier: MIT
"""kernel-doc blocks are read into their own layer; doxygen blocks are not (S6; 2.0.0, index only).

@brief Tests the kernel-doc layer.
@version 1
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from clew.kerneldoc import ingest_kerneldoc, parse_kerneldoc

_SOURCE = """\
/**
 * dev_open() - Open the device.
 * @dev: The device, already probed.
 * @flags: O_* flags; O_NONBLOCK
 *         returns at once.
 *
 * Takes the device lock for the duration.
 *
 * Context: Process context. Sleeps.
 * Return: 0 on success, a negative errno otherwise.
 */
int dev_open(struct device *dev, int flags);

/**
 * struct dev_ops - The operations a driver supplies.
 * @open: Called by dev_open().
 */
struct dev_ops { int (*open)(void); };

/**
 * DOC: Locking
 *
 * Every entry point takes the device lock.
 */

/**
 * @brief A doxygen block, which kernel-doc must leave alone.
 * @param x The value.
 */
int doxy(int x);
"""


def test_a_function_block_is_read_with_its_parameters_and_sections() -> None:
    """@brief Name, brief, @args (with a continuation line), Context and Return."""
    (fn, *_rest) = parse_kerneldoc(_SOURCE)
    assert (fn["kind"], fn["name"], fn["brief"]) == ("function", "dev_open", "Open the device.")
    assert json.loads(fn["params"]) == {
        "dev": "The device, already probed.",
        "flags": "O_* flags; O_NONBLOCK returns at once.",
    }
    assert fn["context"] == "Process context. Sleeps."
    assert fn["returns"] == "0 on success, a negative errno otherwise."
    assert "Takes the device lock" in fn["description"]
    assert fn["line"] == 1


def test_struct_and_doc_blocks_are_read_and_a_doxygen_block_is_not() -> None:
    """@brief `struct foo -` and `DOC:` are kernel-doc; an `@brief` block is doxygen's."""
    blocks = parse_kerneldoc(_SOURCE)
    assert [(b["kind"], b["name"]) for b in blocks] == [
        ("function", "dev_open"),
        ("struct", "dev_ops"),
        ("doc", ""),
    ]
    assert blocks[2]["brief"] == "Locking"


def test_the_layer_records_c_files_only_and_exists_when_empty(tmp_path: Path) -> None:
    """@brief Rows for a C file; a Python file is not read; the table exists with no rows."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "dev.c").write_text(_SOURCE)
    (repo / "tool.py").write_text('"""foo() - not kernel-doc."""\n')
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER)")
    conn.executemany("INSERT INTO path(name, type) VALUES (?, 1)", [("dev.c",), ("tool.py",)])
    conn.commit()
    conn.close()
    assert ingest_kerneldoc(db, repo) == 3
    files = {r[0] for r in sqlite3.connect(db).execute("SELECT file_path FROM kerneldoc")}
    assert files == {"dev.c"}
