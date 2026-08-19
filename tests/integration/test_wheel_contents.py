# SPDX-License-Identifier: MIT
"""A console script the wheel does not carry the module for.

**THIS SHIPPED. TWICE, THROUGH DIFFERENT LAYERS, AND EVERY OTHER CHECK WAS GREEN.**

`clew-hook` is a `PostToolUse` hook, so its failure mode is a `ModuleNotFoundError` on every
`Bash`, `Grep` and `Glob` call a consumer makes — the single loudest way a package can be wrong.
It reached PyPI because `[tool.hatch.build.targets.wheel]` declared

    py-modules = ["clew_hook"]

which is a **setuptools** key. Hatchling neither reads it nor rejects it. The document parsed,
the build succeeded, `twine check` passed, the release workflow's tag/version guard passed, and
the wheel contained `clew/` and nothing else. That is this project's own most-repeated defect —
an accepted-but-unread key — reached through the build backend rather than a declaration file.

**THE EDITABLE INSTALL IS WHY NOTHING LOCAL COULD SEE IT.** `pip install -e .` writes a `.pth`
that puts the source root on `sys.path`, so `import clew_hook` succeeds whether or not any wheel
would carry it. Every unit test, every `pre-commit` run and every hand-invocation of the console
script therefore passed against a layout the published artifact did not have. **The only witness
is the built artifact**, which is why this test builds one instead of reasoning about the config.

**IT IS NOT A CHECK ON THE SPELLING OF THE CONFIG.** Asserting `only-include` is present would
be a check that could be satisfied while still shipping a broken wheel — a different backend, a
`sources` rewrite or a later hatchling would all pass it. The question is only ever *is the
module in the artifact*, so that is what is asked, of a real wheel, for every console script the
package declares.

@brief The built wheel must contain the module behind every declared console script.
@version 1
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from clew.tomlcompat import require_toml_module

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


##
# @brief Build a wheel from the repository into a temporary directory.
# @param out_dir Directory to build into.
# @return Path to the built wheel.
# @version 1
# @dg_internal
def _build_wheel(out_dir: Path) -> Path:
    """`sys.executable`, never a bare `python` — a subprocess test that shells out to whatever
    `python` means on PATH broke CI on all three interpreter legs once already, and the venv rule
    exists for the same reason.

    @brief Build a wheel and return its path.
    @return The built wheel.
    @version 1
    """
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir), str(REPO_ROOT)],
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, built {[w.name for w in wheels]}"
    return wheels[0]


##
# @brief Every declared console script's module must be present in the built wheel.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_wheel_contains_every_console_script_module(tmp_path: Path) -> None:
    """BOTH MODULE SHAPES ARE ACCEPTED, because both are legitimate: `clew.cli` lives at
    `clew/cli.py` inside a package, `clew_hook` is a top-level single module at `clew_hook.py`.
    A check that only understood packages would have called the top-level module missing and a
    check that only understood modules would have called the package one missing, so the target
    is resolved to either spelling and the failure names which one it looked for.

    @brief Each console script's module is in the wheel.
    @return None.
    @version 1
    """
    pyproject = require_toml_module().loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    scripts = pyproject["project"]["scripts"]
    assert scripts, "the package declares no console scripts — the check would pass vacuously"

    wheel = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())

    missing = {}
    for script, target in scripts.items():
        module = target.split(":", 1)[0]
        stem = module.replace(".", "/")
        ## A single module is `<stem>.py`; a package is `<stem>/__init__.py`. Either satisfies an
        ## import, and neither is more correct than the other for an entry point.
        if f"{stem}.py" not in members and f"{stem}/__init__.py" not in members:
            missing[script] = f"{stem}.py or {stem}/__init__.py"

    assert not missing, (
        f"{wheel.name} installs console scripts whose modules it does not contain: {missing}. "
        f"Every one of them raises ModuleNotFoundError the first time a consumer runs it. "
        f"Wheel top level: {sorted({name.split('/')[0] for name in members})}"
    )
