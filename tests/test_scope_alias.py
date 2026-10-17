# SPDX-License-Identifier: MIT
"""`from-guard` names a tool that no longer exists, so `from-declaration` means the same thing.

Group C, 1.1.0 MERGE REVIEW. The value dates from when the index read doxygen-guard's own
`.doxygen-guard.yaml` for its scope — the scope came FROM THE GUARD. It now comes from the
`index_scope:` section of the repo's `.clew.yaml`, which the gate does not read and has no
part in. The spelling is kept because it is recorded in `build_meta` and replayed by later
builds of existing databases, so changing it would strand every index already built; the alias
is what stops a new caller having to learn the history to pass the default.

NOT A CLI CONCERN. `--scope` is no longer a flag — it is a build mechanic on the typed surface
only (`build_index(scope=…)`, `index(action='refresh', scope=…)`), as `clew/cli.py`'s folded-
defaults note states. So this is about what an MCP caller and an embedding caller may pass,
and nothing else.

@brief The `from-declaration` spelling of the declared-scope tier.
@version 1
"""

from __future__ import annotations

import pytest

from clew.scope import SCOPE_DOXYFILE, SCOPE_FROM_DECLARATION, SCOPE_FROM_GUARD, normalize_scope


def test_the_new_spelling_resolves_to_the_recorded_one() -> None:
    """@brief `from-declaration` normalizes to the stored value. @version 1"""
    assert normalize_scope(SCOPE_FROM_DECLARATION) == SCOPE_FROM_GUARD


@pytest.mark.parametrize("value", [SCOPE_FROM_GUARD, SCOPE_DOXYFILE, None])
def test_every_existing_value_is_unchanged(value: str | None) -> None:
    """THE COMPATIBILITY HALF. `from-guard` is written into `build_meta` and replayed by every
    later build of that database, so the alias must not change what the recorded value means.

    @brief Existing values pass through untouched. @version 1
    """
    assert normalize_scope(value) == value


def test_an_unknown_scope_is_returned_for_the_caller_to_refuse() -> None:
    """NORMALIZING IS NOT VALIDATING. The refusal for an unknown scope lives where the Doxyfile
    is resolved and already names the two it accepts; silently mapping an unknown value onto a
    default here would build a boundary the caller did not ask for and report success.

    @brief An unrecognised value is passed through, not defaulted. @version 1
    """
    assert normalize_scope("whatever") == "whatever"


def test_the_served_description_does_not_name_the_gate() -> None:
    """The MCP `scope` parameter described itself as "the repo's own guard declaration", which
    is wrong in the way most likely to mislead: it sends a reader to the `guard:` section,
    which has no `index_scope` in it and never will.

    @brief The scope parameter's description names the declaration, not the gate. @version 1
    """
    import inspect

    from clew.mcp_server import server

    source = inspect.getsource(server)
    assert "the repo's own guard declaration" not in source, (
        "the served description points a caller at the gate's config for a setting the gate "
        "does not read"
    )
