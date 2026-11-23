# SPDX-License-Identifier: MIT
"""Write clew's own SBOM, `bom.cdx.json`, from what the package ships (W-10, 2.0.0).

OWNER REVIEW 2026-11-22: "sbom page doesnt show me anything, we should have an sbom". The wiki's
SBOM page RENDERS a repository's own SBOM and never writes one (owner ruling, #70); clew had none.
Owner Q/A the same day: commit a generated SBOM, made by a standard tool, refreshed at release.

WHAT IT DESCRIBES: clew and its RUNTIME dependencies, not this checkout's development venv (Sphinx,
pytest and the rest of `[dev]` do not ship). So a scratch venv gets `pip install .` and nothing else,
and CycloneDX's own Python tool (`cyclonedx-py environment`, cyclonedx-bom, in `[dev]`) reads it.

    .venv/bin/python scripts/make_sbom.py            # writes bom.cdx.json at the repo root

@brief Generate clew's CycloneDX SBOM.
@version 1
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bom.cdx.json"


## @brief Build a runtime-only venv, read it with cyclonedx-py, write bom.cdx.json.
## @return Exit status.
## @version 1
## @utility
def main() -> int:
    """A FRESH VENV EACH TIME, so a package left over from an earlier install cannot appear.

    @brief Entry point.
    @return 0 on success.
    """
    with tempfile.TemporaryDirectory(prefix="clew-sbom-") as scratch:
        env = Path(scratch) / "venv"
        ## WITHOUT PIP, installed into from this interpreter's pip (`--python`), so pip itself —
        ## which clew does not ship — is not read as a component.
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(env)], check=True)
        py = env / "bin" / "python"
        subprocess.run(
            [sys.executable, "-m", "pip", "--python", str(py), "install", "-q", str(ROOT)],
            check=True,
        )
        subprocess.run(
            [
                str(Path(sys.executable).with_name("cyclonedx-py")),
                "environment",
                "--pyproject",
                str(ROOT / "pyproject.toml"),
                "--output-reproducible",
                "--of",
                "JSON",
                "-o",
                str(OUT),
                str(py),
            ],
            check=True,
        )
    ## ENDS IN A NEWLINE, as the gate's end-of-file-fixer requires; the tool writes none.
    text = OUT.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        OUT.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
