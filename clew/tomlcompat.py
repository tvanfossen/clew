# SPDX-License-Identifier: MIT
"""The single TOML-parser import in this package.

`tomllib` is stdlib from Python 3.11. This package's declared floor is 3.10
(gh#23 — a downstream repo pinned to 3.10.12 on Ubuntu 22.04, which is the LTS
system interpreter, could not install at all), so below 3.11 the `tomli`
backport supplies the same API and `pyproject.toml` declares it conditionally.

**Why this is one module and not a two-line try/except at each call site.** It
already was two call sites, and they had diverged: `shared_key_edges` had the
fallback and `py_entrypoints` did not — it imported `tomllib` bare, inside an
`except (OSError, ValueError, ImportError)` that would have caught the failure
and returned `{}`. Duplicating a compatibility shim is how one copy ends up
without the compatibility.

The two accessors here encode a distinction the old handler could not make:

- `toml_module()` answers "is there a parser", and may answer no. For a caller
  deciding whether a capability exists at all.
- `require_toml_module()` is for a caller about to read a document it needs, and
  raises `TomlParserUnavailableError` when there is none. This is the one to
  reach for by default — returning an empty document because no parser could be
  found is the failure mode gh#23 was filed about.

@brief Compatibility accessor for tomllib / the tomli backport.
@version 1
"""

from __future__ import annotations

from types import ModuleType

from .errors import TomlParserUnavailableError

## Named once so the error message and the `pyproject.toml` marker cannot drift
## into naming different packages.
_BACKPORT = "tomli"


## @brief Return a TOML-parsing module, or None when none is importable.
## @return `tomllib`, else the `tomli` backport, else None.
## @version 2
## @utility
def toml_module() -> ModuleType | None:
    """Prefers the stdlib module so a 3.11+ interpreter never depends on the
    backport being present, and never prefers it if it happens to be.

    Returns None rather than raising, for the caller that is probing rather than
    parsing. A caller that needs a document should use `require_toml_module`;
    a caller that maps None onto an empty result is reintroducing gh#23.

    @brief Import tomllib, falling back to tomli.
    @return The parser module, or None when neither imports.
    @version 2
    """
    try:
        import tomllib

        return tomllib
    except ImportError:
        pass
    try:
        import tomli

        return tomli
    except ImportError:
        return None


## @brief Return a TOML-parsing module, raising when none is importable.
## @return `tomllib`, else the `tomli` backport.
## @version 1
## @utility
def require_toml_module() -> ModuleType:
    """The default accessor. The raise is the whole feature: on 3.10 without the
    backport the alternative is a build that succeeds while silently skipping
    every `pyproject.toml` it was supposed to read.

    The message names the missing distribution rather than describing the
    condition, because the only way to reach it is an install whose conditional
    `tomli` dependency did not arrive, and `pip install tomli` is the fix.

    @brief Import a TOML parser or refuse.
    @return The parser module.
    @version 1
    """
    module = toml_module()
    if module is None:
        raise TomlParserUnavailableError(
            "no TOML parser available: 'tomllib' is stdlib only on Python 3.11+, "
            f"and the '{_BACKPORT}' backport is not installed. "
            f"Install it with: pip install {_BACKPORT}"
        )
    return module
