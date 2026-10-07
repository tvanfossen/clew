# SPDX-License-Identifier: MIT
"""The doxygen gate: presence, revision staleness, tag syntax and requirement coverage.

This package WAS doxygen-guard, a separate distribution clew depended on. It is absorbed
here so the index and the gate parse a target's config with ONE schema, from ONE release,
instead of two independently pinned ones. The config is the `guard:` section of the repo's
`.clew.yaml` (it was a separate `.doxygen-guard.yaml`); its schema and the pre-commit hook id
are doxygen-guard's.

It is OPTIONAL in use, not in install: nothing in the index pipeline runs the gate. A
repo opts in by declaring the `doxygen-guard` hook from this repository, or by running
`clew guard ...` itself.

@brief The absorbed doxygen-guard gate, reachable as `clew guard`.
@version 1
"""

from importlib.metadata import PackageNotFoundError, version

## The upstream doxygen-guard release this package was absorbed from. Kept so a skew
## report can still name a doxygen-guard version a target's own pin can be compared to.
UPSTREAM_BASELINE = "1.4.2"

try:
    __version__ = version("clew-trace")
except PackageNotFoundError:  # pragma: no cover - a source tree without an install
    __version__ = "unknown"
