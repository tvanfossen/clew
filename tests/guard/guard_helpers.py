"""Shared helpers for the absorbed doxygen-guard tests (formerly its tests/conftest.py)."""

from pathlib import Path

import pytest

from clew.guard.config import VALIDATE_DEFAULTS
from clew.guard.parser import ParseSettings

FIXTURES_DIR = Path(__file__).parent / "fixtures"

COMMENT_START = VALIDATE_DEFAULTS["comment_style"]["start"]
COMMENT_END = VALIDATE_DEFAULTS["comment_style"]["end"]
C_PATTERN = VALIDATE_DEFAULTS["languages"]["c"]["function_pattern"]
C_EXCLUDES = VALIDATE_DEFAULTS["languages"]["c"]["exclude_names"]
C_SETTINGS = ParseSettings(comment_start=COMMENT_START, comment_end=COMMENT_END)
CPP_PATTERN = VALIDATE_DEFAULTS["languages"]["cpp"]["function_pattern"]
CPP_EXCLUDES = VALIDATE_DEFAULTS["languages"]["cpp"]["exclude_names"]
CPP_SETTINGS = ParseSettings(comment_start=COMMENT_START, comment_end=COMMENT_END)


@pytest.fixture()
def fixtures_dir():
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


PY_PATTERN = VALIDATE_DEFAULTS["languages"]["python"]["function_pattern"]
PY_EXCLUDES = VALIDATE_DEFAULTS["languages"]["python"]["exclude_names"]
PY_SETTINGS = ParseSettings(
    comment_start=VALIDATE_DEFAULTS["languages"]["python"]["comment_style"]["start"],
    comment_end=VALIDATE_DEFAULTS["languages"]["python"]["comment_style"]["end"],
)

_LANGS = {
    "c": (C_EXCLUDES, C_SETTINGS),
    "cpp": (CPP_EXCLUDES, CPP_SETTINGS),
    "python": (PY_EXCLUDES, PY_SETTINGS),
}


def parse_lang(lang_name: str, content: str, settings=None, skip_fwd=True):
    """Parse source through the production (tree-sitter) path for a language.

    skip_fwd is accepted and ignored: bodyless declarations are always skipped by the
    AST path, and the config knob that pretended otherwise was removed in 1.4.0. The
    parameter remains so existing call sites read unchanged.
    """
    from clew.guard.parser import parse_functions

    excludes, default_settings = _LANGS[lang_name]
    return parse_functions(
        content,
        excludes,
        settings or default_settings,
        lang_name=lang_name,
    )


def parse_c(content: str, settings=None, skip_fwd=True):
    """Parse C source through the production path."""
    return parse_lang("c", content, settings, skip_fwd)


def parse_cpp(content: str, settings=None, skip_fwd=True):
    """Parse C++ source through the production path."""
    return parse_lang("cpp", content, settings, skip_fwd)


def parse_python(content: str, settings=None, skip_fwd=True):
    """Parse Python source through the production path."""
    return parse_lang("python", content, settings, skip_fwd)
