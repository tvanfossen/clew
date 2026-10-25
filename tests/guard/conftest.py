"""Fixtures for the absorbed doxygen-guard tests. The helpers live in guard_helpers.py, which
the test modules import by name — a conftest is not importable as `tests.conftest` here,
because this repo's own `tests/conftest.py` would answer that name."""

from guard_helpers import fixtures_dir  # noqa: F401  (re-exported as a pytest fixture)
