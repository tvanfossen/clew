# SPDX-License-Identifier: MIT
"""The doxygen gate: presence, revision staleness, tag syntax and requirement coverage.

The gate is clew's own: the index and the gate parse a target's config with ONE schema, from
ONE release. Its config is the `guard:` section of the repository's `.clew.yaml`. (It began as
a separate project, doxygen-guard; 2.0.0 is the hard cut — a leftover `.doxygen-guard.yaml` or
`doxygen-guard` hook id is refused, and `@dg_internal` is `@utility`.)

It is OPTIONAL in use, not in install: nothing in the index pipeline runs the gate. A
repository opts in by declaring the `clew-guard` hook from this repository, or by running
`clew guard ...` itself.

@brief clew's doxygen gate, reachable as `clew guard`.
@version 2
"""

from importlib.metadata import PackageNotFoundError, version

## The upstream doxygen-guard release this package was absorbed from. Kept so a skew
## report can still name a doxygen-guard version a target's own pin can be compared to.
UPSTREAM_BASELINE = "1.4.2"

try:
    __version__ = version("clew-trace")
except PackageNotFoundError:  # pragma: no cover - a source tree without an install
    __version__ = "unknown"
