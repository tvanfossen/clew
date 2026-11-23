# SPDX-License-Identifier: MIT
"""An exemption can be required to say why (PG3b; 2.0.0, owner Q/A 2026-11-19).

THE STANDARDS' FORM: DO-178C, ISO 26262 and IEC 62304 accept code that does not trace to a
requirement when the exception is JUSTIFIED. With `guard.validate.exemption_reason: required`,
every `@utility` and `@callback` carries a one-line reason (`@utility parses the header for X`),
which makes an exemption reviewable rather than a silencer.

OFF BY DEFAULT (`optional`): clew has ~1,629 unreasoned exemptions and entropic ~1,890, and a
generated reason would satisfy the gate while saying nothing. A repository turns it on once its
reasons are written. Any other value is refused by name.

@brief Tests the exemption-reason switch.
@version 1
"""

from __future__ import annotations

import pytest

from clew.guard.checks import check_exemption_reasons
from clew.guard.config import CONFIG_DEFAULTS, deep_merge, validate_config_schema
from clew.guard.parser import DoxygenBlock, Function


def _func(tag: str, reason: str) -> Function:
    """@brief A function exempt by one tag with this reason text. @return Function."""
    block = DoxygenBlock(
        start_line=0, end_line=3, tags={"brief": ["B."], "version": ["1.0"], tag: [reason]}
    )
    return Function(name="f", def_line=4, body_end=6, doxygen=block)


_REQUIRED = deep_merge(CONFIG_DEFAULTS, {"validate": {"exemption_reason": "required"}})


@pytest.mark.parametrize("tag", ["utility", "callback"])
def test_a_bare_exemption_is_refused_when_reasons_are_required(tag: str) -> None:
    """@brief No reason, switch on: one violation naming the tag."""
    (v,) = check_exemption_reasons(_func(tag, ""), "a.c", _REQUIRED)
    assert f"@{tag}" in v.message and "reason" in v.message


def test_a_reasoned_exemption_passes() -> None:
    """@brief A one-line reason satisfies it."""
    assert (
        check_exemption_reasons(
            _func("utility", "parses the header for the loader"), "a.c", _REQUIRED
        )
        == []
    )


def test_reasons_are_optional_by_default() -> None:
    """@brief Default: a bare exemption is fine."""
    assert check_exemption_reasons(_func("utility", ""), "a.c", CONFIG_DEFAULTS) == []


def test_an_unknown_setting_is_refused() -> None:
    """@brief `required` or `optional`; anything else named."""
    errors = validate_config_schema({"validate": {"exemption_reason": "mandatory"}})
    assert any("exemption_reason" in e for e in errors), errors
