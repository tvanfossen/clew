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


def _pipeline(root: Path, out: Path) -> Path:
    """@brief One real `clew --repo-root` build, as an operator runs it. @return Database."""
    from clew.cli import _build_argparser, _run_pipeline

    _run_pipeline(_build_argparser().parse_args(["--repo-root", str(root), "--output", str(out)]))
    return out


def test_a_refresh_under_strip_from_path_keeps_inheritance(tmp_path: Path) -> None:
    """ENTROPIC'S RERUN OF 314e4696 (7ea9724): through the real pipeline a doc-only edit to
    adapter_base.h still took compoundref 133 -> 125 and reimplements 248 -> 221, and reverting it
    left 128 / 228. entropic's Doxyfile declares `STRIP_FROM_PATH = include src`, so the cached
    master spells `include/x/base.h` as `x/base.h`; `_incremental_plan` ran `xref_closure` on that
    RAW master, where no row can match the changed file — the closure was the changed file alone,
    for xrefs too. The two-header test above has no stripping and could not see it.

    @brief Edit, refresh and revert under STRIP_FROM_PATH equal fresh builds.
    """
    root = tmp_path / "repo"
    (root / "include" / "x").mkdir(parents=True)
    (root / "src" / "x").mkdir(parents=True)
    (root / "include" / "x" / "base.h").write_text(
        "/** @brief A base. */\nstruct Base {\n  /** @brief Area. */\n  virtual int area() const;\n"
        "  virtual ~Base() {}\n};\n",
        encoding="utf-8",
    )
    (root / "src" / "x" / "derived.h").write_text(
        '#include "x/base.h"\n/** @brief A derived. */\nstruct Derived : Base {\n'
        "  /** @brief Area. */\n  int area() const override;\n};\n",
        encoding="utf-8",
    )
    (root / "Doxyfile").write_text(
        "PROJECT_NAME = strip\nINPUT = include src\nRECURSIVE = YES\nEXTRACT_ALL = YES\n"
        "FULL_PATH_NAMES = YES\nSTRIP_FROM_PATH = include src\nSTRIP_FROM_INC_PATH = include\n",
        encoding="utf-8",
    )
    import subprocess

    from clew.gitenv import git_argv

    subprocess.run(git_argv("init", "-q"), cwd=root, check=True)
    subprocess.run(git_argv("add", "-A"), cwd=root, check=True)
    subprocess.run(
        git_argv("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"),
        cwd=root,
        check=True,
    )
    live = tmp_path / "live" / "clew.db"
    live.parent.mkdir()
    want = _inheritance(_pipeline(root, live))
    assert ("compoundref", "Base>Derived") in want, f"vacuous: {want}"

    base = root / "include" / "x" / "base.h"
    original = base.read_text(encoding="utf-8")
    base.write_text(original.replace("A base.", "A base, reworded."), encoding="utf-8")
    fresh = tmp_path / "fresh" / "clew.db"
    fresh.parent.mkdir()
    assert _inheritance(_pipeline(root, live)) == _inheritance(_pipeline(root, fresh)), "edit"

    base.write_text(original, encoding="utf-8")
    assert _inheritance(_pipeline(root, live)) == want, "revert"
