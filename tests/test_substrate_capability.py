# SPDX-License-Identifier: MIT
"""What the substrate can parse is a measurement, never a version comparison.

1.1.0. The five configuration languages (bash, cmake, yaml, json, markdown) are registered
in a FORK of lang-parsing-substrate, open upstream as PR #1 and not yet released. The fork's
wheel reports version **0.11.2 — the same string as the published wheel**, because the
maintainer owns versions and the PR carries no bump. So `importlib.metadata.version` cannot
tell the two apart, and neither can a pin: a fresh venv or a `pip install -U` silently swaps
the fork for the published wheel.

THEREFORE EVERY FRONT END ASKS WHAT IS COMPILED IN, not what version is installed. With the
published wheel the new keys are simply absent, the front ends register nothing, and the miss
report says those file types are not indexed — a degrade, not a crash. When upstream publishes
the grammars this module starts answering True with no change to clew.

@brief The capability gate over lang-parsing-substrate's compiled-in languages.
@version 1
"""

from __future__ import annotations

import sys
import types

import pytest

from clew import substrate

## Registered by the substrate since long before this release, so a build that cannot see
## these is broken rather than merely older.
_ALWAYS = ("c", "cpp", "python", "rust", "javascript", "typescript")

## The fork's five. Present only while the dev wheel is installed.
_FORKED = ("bash", "cmake", "yaml", "json", "markdown")


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """@brief The gate caches per process; a test that fakes the module must not inherit it."""
    substrate.compiled_languages.cache_clear()
    yield
    substrate.compiled_languages.cache_clear()


def test_the_languages_the_substrate_has_always_had_are_reported() -> None:
    """@brief The gate reads the real module. @version 1"""
    keys = substrate.compiled_languages()
    assert isinstance(keys, frozenset)
    for key in _ALWAYS:
        assert key in keys, f"{key} absent from a substrate that must have it: {sorted(keys)}"


def test_a_language_the_substrate_does_not_have_is_absent() -> None:
    """@brief A negative, so the set is not merely non-empty. @version 1"""
    assert not substrate.has_language("cobol")


def test_the_gate_is_capability_not_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in reporting the PUBLISHED language set while carrying the fork's version
    string is exactly the state a `pip install -U` leaves behind.

    @brief Version 0.11.2 with no bash means has_language('bash') is False. @version 1
    """
    fake = types.ModuleType("lang_parsing_substrate")
    fake.__version__ = "0.11.2"
    fake.languages = lambda: [types.SimpleNamespace(key=k) for k in _ALWAYS]
    monkeypatch.setitem(sys.modules, "lang_parsing_substrate", fake)
    substrate.compiled_languages.cache_clear()

    assert substrate.has_language("c")
    assert not substrate.has_language("bash")
    assert substrate.missing_languages(("c", "bash", "cmake")) == ("bash", "cmake")


def test_missing_languages_is_empty_when_everything_asked_for_is_present() -> None:
    """@brief The empty answer is the one a front end acts on. @version 1"""
    assert substrate.missing_languages(_ALWAYS) == ()


def test_an_unimportable_substrate_degrades_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The substrate is a hard dependency, so this should not happen — but the gate is
    consulted on the gate's path too, and a front end that cannot run must say so rather
    than take the build down.

    @brief No substrate means no languages, not an exception. @version 1
    """
    monkeypatch.setitem(sys.modules, "lang_parsing_substrate", None)
    substrate.compiled_languages.cache_clear()
    assert substrate.compiled_languages() == frozenset()
    assert not substrate.has_language("c")


def test_the_fork_is_installed_in_this_venv() -> None:
    """Not a property of clew — a check that THIS checkout's venv still has the dev wheel,
    so the front-end tests below are exercising real grammars. Rebuild with
    `bash .claude/tmp/substrate-fork.sh` if it fails.

    @brief The dev fork wheel is present. @version 1
    """
    missing = substrate.missing_languages(_FORKED)
    if missing:
        pytest.skip(f"published substrate installed; fork keys absent: {missing}")
    assert substrate.compiled_languages() >= frozenset(_FORKED)
