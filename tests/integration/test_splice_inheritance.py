# SPDX-License-Identifier: MIT
"""An edited base class keeps the classes that derive from it in OTHER files (entropic, 2.0.0).

ENTROPIC'S AUDIT OF f6ff1f7c: after `clew wiki build --refresh` over an index of an older tree,
`ChatAdapter` (include/entropic/inference/adapters/adapter_base.h, edited by 7ea9724) had no
derived classes, where a fresh full build of the same tree has 5 product + 3 test. Measured on
entropic 7ea9724: refreshed `compoundref` 125 rows, fresh 133 — the 8 missing were exactly
ChatAdapter → its derived adapters.

The cause: `xref_closure` closes over call/reference edges only. A derived class in another
header usually holds no xref into its base's file, so its file never joins the subset run;
doxygen cannot emit a `compoundref` whose derived end it never saw; and the splice had deleted the
edited file's compoundref rows. Inheritance and overrides are edges a subset run needs both ends
of, exactly like an xref.

@brief Tests that the splice keeps cross-file inheritance when the base's file changes.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.doxygen import run_doxygen
from clew.doxygen_splice import include_expansion, splice_doxygen, xref_closure

pytestmark = pytest.mark.integration


def _run(doxyfile: Path, work: Path, root: Path, subset: list[str] | None = None) -> Path:
    """@brief Run doxygen over the tree or a subset. @return Database path."""
    work.mkdir(parents=True, exist_ok=True)
    return run_doxygen(
        doxyfile,
        work,
        extra_input=[str(root / p) for p in subset] if subset else None,
        replace_input=bool(subset),
        output_dir=work,
    )


def _inheritance(db: Path) -> set[tuple[str, str]]:
    """@brief (base, derived) by name, and (overrider, overridden) by qualified member. @return Set."""
    conn = sqlite3.connect(db)
    try:
        bases = {
            ("compoundref", f"{b}>{d}")
            for b, d in conn.execute(
                "SELECT b.name, d.name FROM compoundref x JOIN compounddef b ON b.rowid = x.base_rowid "
                "JOIN compounddef d ON d.rowid = x.derived_rowid"
            )
        }
        overrides = {
            ("reimplements", f"{a}>{b}")
            for a, b in conn.execute(
                "SELECT m.scope || '::' || m.name, o.scope || '::' || o.name FROM reimplements r "
                "JOIN memberdef m ON m.rowid = r.memberdef_rowid "
                "JOIN memberdef o ON o.rowid = r.reimplemented_rowid"
            )
        }
    finally:
        conn.close()
    return bases | overrides


def test_editing_a_base_class_keeps_its_derived_classes_in_other_files(tmp_path: Path) -> None:
    """THE BASE'S FILE IS THE ONLY CHANGE, and the derived class's file has no call into it — the
    shape of entropic's adapters. A full rebuild is the ground truth.

    @brief Cross-file inheritance survives a splice of the base's file.
    """
    root = tmp_path / "repo"
    (root / "include").mkdir(parents=True)
    (root / "include" / "base.h").write_text(
        "/** @brief A base. */\nstruct Base {\n  /** @brief Area. */\n  virtual int area() const;\n"
        "  virtual ~Base() {}\n};\n",
        encoding="utf-8",
    )
    (root / "include" / "derived.h").write_text(
        '#include "base.h"\n/** @brief A derived. */\nstruct Derived : Base {\n'
        "  /** @brief Area. */\n  int area() const override;\n};\n",
        encoding="utf-8",
    )
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        f"PROJECT_NAME = inh\nINPUT = {root}\nGENERATE_SQLITE3 = YES\nEXTRACT_ALL = YES\n"
        "REFERENCED_BY_RELATION = YES\nREFERENCES_RELATION = YES\n",
        encoding="utf-8",
    )
    master = tmp_path / "master-kept.db"
    shutil.copy2(_run(doxyfile, tmp_path / "master", root), master)

    ## A DOC-ONLY EDIT TO THE BASE, as 7ea9724 was.
    base = root / "include" / "base.h"
    base.write_text(base.read_text().replace("A base.", "A base, reworded."), encoding="utf-8")
    changed = {"include/base.h"}

    truth = tmp_path / "truth-kept.db"
    shutil.copy2(_run(doxyfile, tmp_path / "truth", root), truth)
    want = _inheritance(truth)
    assert ("compoundref", "Base>Derived") in want, (
        f"vacuous: the rebuild has no inheritance {want}"
    )
    assert ("reimplements", "Derived::area>Base::area") in want, f"vacuous: no override {want}"

    subset = sorted(xref_closure(master, changed, root))
    subset_db = _run(doxyfile, tmp_path / "subset", root, subset=subset)
    extra = include_expansion(subset_db, master, changed, set(subset), root)
    if extra:
        subset = sorted(set(subset) | extra)
        subset_db = _run(doxyfile, tmp_path / "subset2", root, subset=subset)
    spliced = tmp_path / "spliced.db"
    report = splice_doxygen(master, subset_db, changed, spliced, root)

    assert not report.skipped, report.skipped
    assert _inheritance(spliced) == want, (
        f"subset {subset}: the splice lost cross-file inheritance — missing "
        f"{sorted(want - _inheritance(spliced))}"
    )
