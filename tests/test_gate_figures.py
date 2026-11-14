# SPDX-License-Identifier: MIT
"""Tests for scripts/gate_figures.py — the per-repo gate the 1.4.0 pre-registration states.

THE TEST THAT MATTERS reproduces a published run. 1.3.0-final's per-repo figures were published
and then used as the 1.4.0 comparator; a script that cannot reproduce them from the committed
sidecars is computing something else, and the gate it reports would be a claim without a method.

@brief Tests for the per-repo gate figures.
@version 1
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gate_figures", REPO / "scripts" / "gate_figures.py")
assert _spec and _spec.loader
gate_figures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate_figures)

## Published in acceptance/runs/1.4.0-pending/PRE-REGISTRATION.md as 1.3.0-final measured.
PUBLISHED = {
    "mattermost": (13.6, 28.2, 1.37, 6.79),
    "mbedtls": (-17.0, 27.8, 2.55, 2.60),
    "self": (-70.0, -57.7, -5.92, -8.72),
    "entropic": (-34.6, 20.6, -7.01, -0.76),
}


@pytest.mark.parametrize("target", sorted(PUBLISHED))
def test_reproduces_the_published_1_3_0_final_figures(target: str) -> None:
    """@brief The committed 1.3.0-final sidecars give the published per-repo figures."""
    run = REPO / "acceptance" / "runs" / "1.3.0-final"
    fig = gate_figures.repo_figures(run, target)
    tok_io, tok_ix, sep_io, sep_ix = PUBLISHED[target]
    assert round(fig["index_only"]["tokens_pct"], 1) == tok_io
    assert round(fig["index"]["tokens_pct"], 1) == tok_ix
    assert round(fig["index_only"]["separation"], 2) == sep_io
    assert round(fig["index"]["separation"], 2) == sep_ix


def test_the_gate_is_cost_lower_and_quality_within_tolerance() -> None:
    """@brief Both conditions, per the pre-registration; either failing is a miss, and named."""
    base = {"tokens_pct": 10.0, "separation": 0.0}
    assert gate_figures.gate(base, {"tokens_pct": 9.9, "separation": -3.0}) == (True, True)
    assert gate_figures.gate(base, {"tokens_pct": 10.0, "separation": 0.0}) == (False, True)
    assert gate_figures.gate(base, {"tokens_pct": 0.0, "separation": -3.01}) == (True, False)
