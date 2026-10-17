# SPDX-License-Identifier: MIT
"""What the substrate can parse, asked of the substrate itself.

WHY THIS IS NOT A VERSION CHECK. The five configuration languages — bash, cmake, yaml,
json, markdown — are registered in a fork of lang-parsing-substrate that is open upstream
and not yet released. The fork's wheel reports version **0.11.2, the same string as the
published wheel**, because versions belong to that project's maintainer and the pull
request carries no bump. `importlib.metadata.version` therefore cannot tell a wheel that
has these grammars from one that does not, and a pin cannot either: a fresh venv or a
`pip install -U` silently restores the published wheel.

So every front end asks what is COMPILED IN. Against the published wheel the keys are
absent, the front ends register nothing, and the miss report names those file types as
not indexed — a degrade with an explanation, not a crash and not a silent gap. When the
grammars are released this module begins answering True and no other clew code changes.

ABSENCE IS NOT AN ERROR HERE. The substrate is a hard dependency of clew and an
unimportable one is a broken install, but this gate is also consulted on the pre-commit
gate's path, where taking the build down to report a missing optional grammar would be
the worse failure. An unimportable substrate yields no languages and logs it.

@brief The compiled-in language set, and the questions front ends ask of it.
@version 1
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from ._common import logger


## @brief Every language key this substrate build can parse.
## @return The keys from `lang_parsing_substrate.languages()`, empty when it cannot be read.
## @version 1
## @req REQ-DDB-PIPE-012
@lru_cache(maxsize=1)
def compiled_languages() -> frozenset[str]:
    """Cached: the answer is fixed for the life of the process, since it is decided by
    which cargo features the installed wheel was built with. Tests clear the cache.

    @brief The substrate's compiled-in language keys.
    @return A frozenset of keys, possibly empty.
    """
    try:
        import lang_parsing_substrate as lps

        return frozenset(info.key for info in lps.languages())
    except (ImportError, AttributeError) as exc:
        ## Not `logger.debug`: a build that silently indexes nothing is the failure this
        ## project exists to avoid, and the operator cannot see a debug line.
        logger.error("lang-parsing-substrate reports no languages (%s)", exc)
        return frozenset()


## @brief Whether this substrate build can parse one language.
## @param key A substrate language key, as `languages()` spells it.
## @return True when the grammar is compiled in.
## @version 1
## @req REQ-DDB-PIPE-012
def has_language(key: str) -> bool:
    """@brief Capability test for one language key."""
    return key in compiled_languages()


## @brief Which of the asked-for languages this substrate build lacks.
## @param keys The language keys a caller needs.
## @return The absent ones, in the order asked; empty when all are present.
## @version 1
## @req REQ-DDB-PIPE-012
def missing_languages(keys: Iterable[str]) -> tuple[str, ...]:
    """Order follows the caller's, not the set's, so a logged or served list reads the
    way the caller wrote it rather than in hash order.

    @brief The absent subset of the asked-for keys.
    @return A tuple of missing keys.
    """
    present = compiled_languages()
    return tuple(key for key in keys if key not in present)
