# SPDX-License-Identifier: MIT
"""What the substrate can parse, asked of the substrate itself.

WHY THIS IS NOT A VERSION CHECK. The five configuration languages — bash, cmake, yaml,
json, markdown — are published from lang-parsing-substrate 0.12.0, which clew requires. A
version still cannot say which grammars a wheel carries: the language set is fixed by the
cargo features it was built with, and a locally built wheel can report the published
version string with a different set. `importlib.metadata.version` cannot tell those apart.

So every front end asks what is COMPILED IN. Against a wheel that lacks a key, the front
ends register nothing for it, and the miss report names those file types as not indexed —
a degrade with an explanation, not a crash and not a silent gap.

ABSENCE IS NOT AN ERROR HERE. The substrate is a hard dependency of clew and an
unimportable one is a broken install, but this gate is also consulted on the pre-commit
gate's path, where taking the build down to report a missing optional grammar would be
the worse failure. An unimportable substrate yields no languages and logs it.

@brief The compiled-in language set, and the questions front ends ask of it.
@version 2
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
