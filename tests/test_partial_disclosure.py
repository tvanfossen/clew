# SPDX-License-Identifier: MIT
"""A partial index must say it is partial on every reply, and must not claim a definitive empty.

A doxygen failure now builds without the C/C++ layer and stamps `diagnostics.doxygen = failed`
with a reason. A stamp nobody reads changes nothing: a query asking for a C function would get
an empty result carrying the standard note — "a definitive empty result ... do not retry" — from
an index that never looked at C. That is the exact failure `absence is not emptiness` names, and
the stamp exists to prevent it only if a reply carries it.

SO IT RIDES THE EXISTING ENVELOPE. `freshness.notices()` already builds the per-reply block of
"what is wrong with this index and what to do"; `_withdraw_definitive` already strips a
definitive-negative claim when a layer may be missing. A partial index is not STALE — it is
current and complete in every layer but one — so it gets its own axis rather than borrowing
`schema`, whose remedy (refresh with force) would only re-run the doxygen that crashed.

@brief Tests that a stamped partial index discloses itself in replies.
@version 1
"""

from __future__ import annotations

from clew.mcp_server import freshness
from clew.mcp_server.tools_query import _withdraw_definitive

_REASON = "doxygen exited with status 134 after parsing 1 file(s): terminate called"

## The note an empty search carries, in the shape `_DEFINITIVE_CLAIMS` matches.
_DEFINITIVE_NOTE = (
    "No symbol matched. This is a definitive empty result from the database. Do not retry this "
    "query or fall back to guessing."
)


## @brief A status payload whose diagnostics carry a doxygen outcome.
## @param outcome The stamped `diagnostics.doxygen` value.
## @return A minimal db_status-shaped mapping.
## @version 1
def _status(outcome: str) -> dict[str, object]:
    """@brief Build a status payload.
    @return Mapping.
    """
    diagnostics = {"doxygen": outcome}
    if outcome == "failed":
        diagnostics["doxygen_reason"] = _REASON
    return {"diagnostics": diagnostics, "source_changed_files": 0}


## @brief The axes a status produces.
## @param status A status payload.
## @return Notices keyed by axis.
## @version 1
def _axes(status: dict[str, object]) -> dict[str, str]:
    """@brief Collect notices by axis.
    @return Axis to message.
    """
    return {n["axis"]: n["message"] for n in freshness.notices(status, code={})}


## @brief A failed doxygen produces a partial notice naming the cause.
## @return None.
## @version 1
def test_a_failed_doxygen_produces_a_partial_notice_with_its_reason() -> None:
    """@brief The partial axis fires and carries the stamped reason.
    @return None.
    @version 1
    """
    axes = _axes(_status("failed"))
    assert "partial" in axes, f"no partial notice: {axes}"
    assert "134" in axes["partial"], f"the reason did not reach the reader: {axes['partial']}"


## @brief Skipped and ran produce no partial notice.
## @return None.
## @version 1
def test_skipped_or_ran_produces_no_partial_notice() -> None:
    """EMPTY ON A HEALTHY INDEX IS THE LOAD-BEARING HALF — `notices()`'s own docstring: "a
    warning that is always present is a warning nobody reads". A TypeScript repo that skipped
    doxygen is COMPLETE, and flagging it would teach every such user to ignore the axis.

    @brief No false positives.
    @return None.
    @version 1
    """
    for outcome in ("skipped", "ran"):
        assert "partial" not in _axes(_status(outcome)), f"{outcome} was flagged as partial"
    assert "partial" not in _axes({"source_changed_files": 0}), "an unstamped index was flagged"


## @brief The partial notice does not prescribe a refresh that would crash again.
## @return None.
## @version 1
def test_the_partial_notice_says_to_fix_the_cause_before_refreshing() -> None:
    """A REFRESH ALONE RE-RUNS THE DOXYGEN THAT CRASHED. The schema axis's remedy is "refresh with
    force", which is right there and wrong here; borrowing it would send the reader round a loop.

    @brief The remedy names the cause.
    @return None.
    @version 1
    """
    message = _axes(_status("failed"))["partial"].lower()
    assert "index_scope" in message or "cause" in message, f"no remedy beyond refresh: {message}"


## @brief A definitive empty claim is withdrawn on a partial index.
## @return None.
## @version 1
def test_a_definitive_empty_is_withdrawn_on_a_partial_index() -> None:
    """@brief "Definitive" does not survive a missing layer.
    @return None.
    @version 1
    """
    payload = {"note": _DEFINITIVE_NOTE, "found": False}
    _withdraw_definitive(payload, [{"axis": "partial", "message": "x"}])
    note = payload["note"].lower()
    assert "this is a definitive" not in note, f"the definitive claim survived: {payload['note']}"
    assert "c/c++" in note, f"the withdrawal does not say which layer is missing: {payload['note']}"
