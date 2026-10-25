# SPDX-License-Identifier: MIT
"""What the substrate can parse is a measurement, never a version comparison.

The five configuration languages (bash, cmake, yaml, json, markdown) are published from
lang-parsing-substrate 0.12.0, which clew requires. Which grammars a wheel carries is fixed by
the cargo features it was built with, not by its version string — a locally built wheel can
report the published version with a different set — so `importlib.metadata.version` cannot
answer the question.

THEREFORE EVERY FRONT END ASKS WHAT IS COMPILED IN, not what version is installed. With a
wheel that lacks a key, the front ends register nothing for it, and the miss report says
those file types are not indexed — a degrade, not a crash.

@brief The capability gate over lang-parsing-substrate's compiled-in languages.
@version 2
"""

from __future__ import annotations

import sys
import types

import pytest

from clew import substrate

## Registered by the substrate since long before this release, so a build that cannot see
## these is broken rather than merely older.
_ALWAYS = ("c", "cpp", "python", "rust", "javascript", "typescript")

## Published from 0.12.0, the floor clew's dependency range sets.
_CONFIGURATION = ("bash", "cmake", "yaml", "json", "markdown")


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
    """A stand-in carrying a version that publishes bash while reporting a language set
    without it is the state a wheel built with fewer cargo features leaves behind.

    @brief Version 0.12.0 with no bash means has_language('bash') is False. @version 2
    """
    fake = types.ModuleType("lang_parsing_substrate")
    fake.__version__ = "0.12.0"
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


def test_the_required_substrate_has_the_configuration_languages() -> None:
    """Not a property of clew — a check that THIS venv's wheel meets the dependency floor,
    so the front-end tests that skip on a missing grammar are exercising real grammars
    rather than skipping in silence.

    @brief The installed wheel carries all five configuration grammars. @version 2
    """
    missing = substrate.missing_languages(_CONFIGURATION)
    assert not missing, f"lang-parsing-substrate>=0.12.0 is required; absent: {missing}"
