# SPDX-License-Identifier: MIT
"""The PREPROCESSOR CONFIGURATION a build indexes — declared, never guessed.

gh#17. Doxygen evaluates `#if defined(X)` while it parses, so code behind a macro
the build never supplied is not "poorly documented" — it is ABSENT. Nothing in
this pipeline set `PREDEFINED`: every occurrence of the word was prose, in
warnings advising an owner to go and edit their own Doxyfile.

WHY THAT ADVICE WAS NOT ENOUGH, and why this module exists rather than a longer
warning. Two sibling issues already measured the shape of the hole. gh#6 counted
files yielding at most one symbol and found 51.5% of mbedtls barren. gh#11 then
recovered the missing function definitions from the source text with tree-sitter
and took the barren ratio to 13.0% — while `undocumented_ratio` STAYED at 51.5%,
because a preprocessor that skipped the code skipped its doc comment too. A
recovered row carries a name, a file and a line span; it carries no brief, no
documented parameters and no `@req` tag. The GRAPH was recoverable without the
configuration. The PROSE is not. Declaring the configuration is the only thing
that recovers it, which is why gh#11's own docstring calls this the better fix.

THREE THINGS, and the third stands alone::

    # <repo>/.clew.yaml, or the `x-clew:` section of
    # .doxygen-guard.yaml (the passthrough — no second file to maintain)
    preprocessor:
      predefined:                       # (1) explicit, and always wins
        - MBEDTLS_SSL_TLS_C
        - MBEDTLS_SSL_PROTO_TLS1_3
        - MBEDTLS_MAX_BLOCK_LENGTH=16
      config_header: include/mbedtls/mbedtls_config.h   # (2) or `auto`

(3) is that WHICHEVER of those happened is written into `build_meta` under a
`preprocessor.` prefix. An index of a multi-variant codebase is an index of ONE
variant, and until now nothing said which — so two indexes of the same repo could
disagree about whether a function exists at all, with no field to explain it. That
is worth having even with (1) and (2) scoped out, and it is the reason `as_meta`
records a macro COUNT OF ZERO rather than dropping it: "the owner declared a
configuration and it produced nothing" is a finding, and it is the finding a
misspelled path produces.

## `auto` IS OPT-IN, AND THAT IS THE WHOLE DESIGN

A generated config header DOES NOT EXIST UNTIL A BUILD RUNS, so scanning for one
by default is unsound in both directions: absent, the index silently represents
the unconfigured variant; present, it represents whatever the last developer
happened to build, which no consumer declared and no CI reproduces. And many
Kconfig projects ALSO ship a hand-written mock config header for unit tests —
discovering that would index a configuration nobody ships, dressed in the
authority of a recorded declaration.

So the DECISION to discover is declared (`config_header: auto`) and the discovery
itself refuses to guess, following `precommit.discover_guard_config` exactly: a
fixed set of conventional locations, every one of them named in the log, and a
REFUSAL when two or more exist. A repo that declares nothing gets nothing —
byte-identical behaviour to before this module.

`_CONVENTIONAL_HEADERS` deliberately contains no `*_config.h` glob, though gh#17
suggests one. `include/mbedtls/mbedtls_config.h`, `include/psa/crypto_config.h`
and `tests/include/test/mock_config.h` all match it, they describe three
different configurations, and only the owner knows which one an index should
represent. A glob is how the wrong one gets chosen silently; naming the file is
one line of YAML. No conventional location lies under a test or mock directory,
for the same reason — that path is reachable only by naming it, where the
recorded `preprocessor.config_header` says plainly what was used.

## WHAT THE HEADER SCAN IS, PRECISELY

A FLAT `#define` SCAN. It is not a preprocessor and does not pretend to be: it
does not evaluate the `#if` blocks it walks through, so a define inside a
conditional is harvested regardless of whether that conditional would hold. This
is the right trade for the job — mbedtls's config header states its
configuration as top-level `#define`s and comments out the rest, so a flat scan
reads exactly the intended variant — but it is a limitation to state rather than
discover. `#undef` IS honoured, because a header that revokes a macro and is read
as defining it would be worse than not reading it at all.

@brief Resolve and record the preprocessor configuration a build indexes.
@version 1
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._common import logger

## The declaration section this module owns. Registered in
## `declaration.KNOWN_SECTIONS`, so a misspelling is REFUSED rather than parsed into a
## mapping nothing reads — the failure mode that allow-list exists for.
SECTION_PREPROCESSOR = "preprocessor"

## Keys inside the section.
KEY_PREDEFINED = "predefined"
KEY_CONFIG_HEADER = "config_header"

## The `config_header` value that asks for conventional discovery instead of naming a
## path. Spelled as a word rather than `true` so the YAML reads as a choice between
## "this file" and "go and look", which is what it is.
CONFIG_HEADER_AUTO = "auto"

## Provenance values for `preprocessor.source`. Per-module constants rather than
## `vocabulary.py` entries, matching `scope.py` and `precommit.py`: these are
## `build_meta` strings, and `vocabulary.py` is the source for values a DDL CHECK
## constrains.
SOURCE_NONE = "none"
SOURCE_FLAG = "flag"
SOURCE_DECLARED = "declared"
SOURCE_CONFIG_HEADER = "config_header"
SOURCE_BOTH = "declared+config_header"

## Conventional locations for a GENERATED config header, searched only when the repo
## declares `config_header: auto`. Each is a build system's own fixed output path, not
## a pattern — see the module docstring on why there is no `*_config.h` glob and why
## nothing here lies under a test directory.
_CONVENTIONAL_HEADERS = (
    "include/generated/autoconf.h",  # Kconfig: Linux, Zephyr, Buildroot
    "build/config/sdkconfig.h",  # ESP-IDF
    "autoconf.h",  # autotools, in-tree build
    "config.h",  # autotools ./configure output
)

## A `defined(X)` or `defined X` test — the ONLY atom `evaluate_condition` can decide.
## Everything else in `#if` grammar (arithmetic, comparisons, a bare `#if X` read as a
## value, `__has_include`) matches nothing here and is therefore reported UNKNOWN rather
## than guessed at. gh#35 exists because a guess in this position invented a call edge.
_DEFINED = re.compile(r"^defined\s*\(\s*([A-Za-z_]\w*)\s*\)$|^defined\s+([A-Za-z_]\w*)$")


## @brief Split a preprocessor expression on a boolean operator, outside parentheses.
## @param text The expression text.
## @param op Either `&&` or `||`.
## @return The operands; a single-element list when the operator is absent at top level.
## @version 1
## @dg_internal
def _split_top(text: str, op: str) -> list[str]:
    """Depth-tracked rather than `text.split(op)`, because `defined(A) && (B || C)` must
    not be cut inside the parenthesised group — and because `defined(...)` puts
    parentheses in every expression this function will ever see.

    @brief Split on a top-level boolean operator.
    @return List of operand substrings.
    @version 1
    """
    parts: list[str] = []
    depth = start = i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and text.startswith(op, i):
            parts.append(text[start:i])
            i += len(op)
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return parts


## @brief Combine operand verdicts under AND or OR, propagating UNKNOWN.
## @param vals The operands' verdicts, each True, False or None.
## @param decisive True for OR (a single True decides), False for AND.
## @return The combined verdict, or None when no operand decides it.
## @version 1
## @dg_internal
def _combine(vals: list[bool | None], decisive: bool) -> bool | None:
    """Short-circuit semantics deliberately, not "any unknown poisons the result":
    `defined(A) || <arithmetic we cannot read>` is TRUE when A is defined, and treating
    it as unknown would weaken an edge whose branch really is determined. The decisive
    value is checked FIRST for exactly that reason.

    @brief Fold operand verdicts, keeping UNKNOWN only when it changes the answer.
    @return Combined verdict or None.
    @version 1
    """
    if any(v is decisive for v in vals):
        return decisive
    if any(v is None for v in vals):
        return None
    return not decisive


## @brief Decide a single `defined(X)`/`!defined(X)` atom.
## @param text The atom's text, already stripped.
## @param defined The macro names this configuration defines.
## @return True, False, or None when the atom is not a `defined` test.
## @version 1
## @dg_internal
def _atom(text: str, defined: frozenset[str]) -> bool | None:
    """@brief Evaluate a `defined` atom against the configured macros.

    @return True/False, or None when the text is something else.
    @version 1
    """
    if text.startswith("!"):
        inner = evaluate_condition(text[1:], defined)
        return None if inner is None else not inner
    match = _DEFINED.match(text)
    if match is None:
        return None
    return (match.group(1) or match.group(2)) in defined


## @brief Strip one layer of parentheses that encloses a whole expression.
## @param text The expression text, already stripped.
## @return The text with fully-enclosing parentheses removed.
## @version 1
## @dg_internal
def _unwrap(text: str) -> str:
    """Only strips when the OPENING paren closes at the very end — `(A) && (B)` also
    starts with `(` and ends with `)` and must be left alone, which a naive
    startswith/endswith test would break.

    @brief Remove redundant outer parentheses.
    @return The unwrapped expression.
    @version 1
    """
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for i, ch in enumerate(text):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and i < len(text) - 1:
                return text
        text = text[1:-1].strip()
    return text


## @brief Evaluate a preprocessor `#if` condition against a declared configuration.
## @param text The condition expression, as written in the source.
## @param defined The macro names the declared configuration defines.
## @return True (branch live), False (branch dead), or None (cannot be decided).
## @version 1
## @req REQ-DDB-CONFIG-004
def evaluate_condition(text: str, defined: frozenset[str]) -> bool | None:
    """gh#35's decision procedure. Handles `defined(X)`, `!defined(X)`, `&&`, `||` and
    parentheses — which is the whole of what guards a conditional binding in practice —
    and reports None for everything else.

    NONE IS THE LOAD-BEARING RETURN. It is the difference between "this branch is dead,
    drop its edge" and "we do not know which branch is live, so grade both down". A
    version of this that fell back to False would silently DELETE the live edge of any
    binding guarded by an expression it could not parse, which is strictly worse than the
    over-complete graph gh#35 is fixing. `||` is folded short-circuit for the same
    reason: an unknown operand beside a decisive one must not weaken a known answer.

    OR binds looser than AND in C, so `||` is split first and `&&` within each operand.

    @brief Decide whether a preprocessor condition holds under a configuration.
    @return True, False, or None when undecidable.
    @version 1
    """
    stripped = _unwrap(text.strip())
    ors = _split_top(stripped, "||")
    if len(ors) > 1:
        return _combine([evaluate_condition(p, defined) for p in ors], decisive=True)
    ands = _split_top(stripped, "&&")
    if len(ands) > 1:
        return _combine([evaluate_condition(p, defined) for p in ands], decisive=False)
    return _atom(stripped, defined)


## An object-like `#define`. The `(?=\s|$)` is what excludes FUNCTION-LIKE macros
## without a second test: a `#define F(x)` has `(` where this requires whitespace or
## end-of-line. Feeding doxygen a function-like macro harvested out of context is a
## different and riskier operation than stating a configuration, and gh#17 asks for the
## latter.
_DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(?=\s|$)(.*)$")
_UNDEF = re.compile(r"^\s*#\s*undef\s+([A-Za-z_]\w*)(?=\s|$)")

## Trailing comments on a `#define` line are part of the line, NOT part of the value.
## `#define MBEDTLS_MAX_BLOCK_LENGTH 16 /* bytes */` must yield `16`.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


## @brief The preprocessor configuration a build indexed, and where it came from.
## @version 1
@dataclass(frozen=True)
class PreprocessorConfig:
    """The macro list handed to doxygen as `PREDEFINED`, plus the provenance that makes
    it answerable later: which source decided it, and which config header (repo-relative)
    was read.

    `searched` exists for the same reason `precommit.GuardConfigLocation.searched` does.
    A declared `auto` that finds nothing leaves the index representing the unconfigured
    variant, and doing that without saying WHERE we looked is the silence gh#16 named:
    the build succeeds and nothing distinguishes "this repo generates no config header"
    from "we looked in the wrong place".

    Paths are REPO-RELATIVE, always. `build_meta` is published over MCP, and stamping an
    absolute path here would reintroduce the machine-layout disclosure that forced the
    build-version-9 bump.

    @brief A resolved preprocessor configuration with its provenance.
    @version 1
    """

    macros: tuple[str, ...] = ()
    source: str = SOURCE_NONE
    config_header: str | None = None
    searched: tuple[str, ...] = ()
    ## Macros the OPERATOR stated that the repository's own config header does NOT define — i.e.
    ## the ones this build turned ON that ship OFF.
    ##
    ## WHY THE SPLIT IS WORTH KEEPING. `macros` is the union and answers "which variant is this".
    ## It cannot answer "does the repository ship this ON", and the two get confused in the worst
    ## possible direction: measured on mbedtls, an agent asked whether threading is enabled by
    ## default, saw `MBEDTLS_THREADING_C` sitting in `configured_macros`, and had no way to learn
    ## that the symbol is COMMENTED OUT in `mbedtls_config.h` and appears there only because this
    ## build declared it. A confidently wrong answer, not an absent one.
    ##
    ## The membership is the whole signal: a name here ships OFF, a name in `macros` but not here
    ## was READ from the repository's own header and therefore ships ON. Nothing else needs storing
    ## — the header's own state IS the default.
    stated_only: tuple[str, ...] = ()

    ## @brief Whether the target stated a preprocessor configuration at all.
    ## @return True when any source contributed, even if it yielded no macros.
    ## @version 1
    ## @req REQ-DDB-CONFIG-004
    @property
    def declared(self) -> bool:
        """NOT `bool(self.macros)`. A declared config header that yielded zero macros is
        a DECLARATION that produced nothing — which is what a misspelled path or an
        unbuilt `autoconf.h` looks like — and it must be recorded, not read as "the owner
        said nothing".

        @brief Did the target state a configuration?
        @return True when source is anything but none.
        @version 1
        """
        return self.source != SOURCE_NONE

    ## @brief The bare macro NAMES this configuration defines.
    ## @return Frozen set of names, with the doxygen token quoting and any `=value` removed.
    ## @version 2
    ## @req REQ-DDB-CONFIG-004
    @property
    def defined_names(self) -> frozenset[str]:
        """`macros` holds already-rendered doxygen PREDEFINED tokens — `'"NAME"'` or
        `'"NAME=value"'`, double quotes included — because rendering the Doxyfile is what
        it was built for. Asking "is X defined" of that shape needs the quoting and the
        value stripped, and doing it HERE keeps every caller from respelling the same two
        string operations and drifting on one of them.

        A macro defined to `0` still counts as DEFINED, because that is what `defined(X)`
        means to the preprocessor. Evaluating `#if X` as arithmetic is a different question
        this type deliberately does not answer — see `evaluate_guard`, which reports
        UNKNOWN rather than guessing.

        THE OPERATION MOVED TO `bare_macro_names` AND THE WARNING ABOVE IS WHY. A second caller
        did respell it and did drift on one of the two: `kconfig_gates.declared_macro_names`
        stripped `=value` and NOT the quoting, so every macro a build actually declared was
        labelled `undeclared` in `kconfig_gates.origin` — a whole configuration reported absent,
        confidently. It survived because its own test fed it UNQUOTED input, which is the
        recorded shape "the fixture matched the detector rather than the world". Both callers now
        share one function, so a fix reaches both.

        @brief Bare names of the defined macros.
        @return Frozen set of macro names.
        @version 2
        """
        return bare_macro_names(self.macros)

    ## @brief Flatten to string values for build_meta persistence.
    ## @return Mapping of unprefixed preprocessor keys to string values.
    ## @version 2
    ## @req REQ-DDB-CONFIG-004
    def as_meta(self) -> dict[str, str]:
        """gh#17 part 3, and the part that stands on its own. An index of a
        multi-variant codebase is an index of one variant; before this, nothing in the
        database said which, so two indexes of one repo could disagree about whether a
        function EXISTS with no field to explain it.

        Empty strings are returned rather than omitted keys because
        `write_build_signature` drops falsy values — so a build that declared nothing
        writes no `preprocessor.*` rows at all, and an absent key honestly reads as "not
        recorded". `macro_count` is the deliberate exception: it is `"0"` when a
        configuration was declared and produced nothing, and `"0"` is truthy where `0`
        is not. That is the measured-zero rule `coverage.as_meta` documents.

        The macro list is written IN FULL, untruncated. It is the answer to "which
        variant is this", and a truncated answer to that is not one.

        @brief Preprocessor configuration as build_meta values.
        @return Unprefixed key -> string value.
        @version 2
        """
        if not self.declared:
            return {}
        return {
            "source": self.source,
            "config_header": self.config_header or "",
            "macro_count": str(len(self.macros)),
            "predefined": " ".join(self.macros),
            "searched": ", ".join(self.searched),
            ## Written even when empty is NOT possible here — `write_build_signature` drops falsy
            ## values — so an absent key honestly reads as "this build made no statement about the
            ## repository's own defaults", which is the case when no config header was read.
            "stated_only": ", ".join(self.stated_only),
        }


## @brief Strip comments and a trailing line-continuation from a #define's value.
## @param text Raw text following the macro name.
## @return The cleaned value, empty when the macro is object-like with no value.
## @version 1
## @dg_internal
def _clean_value(text: str) -> str:
    """@brief Remove block and line comments from a macro value.

    @return The trimmed value text.
    @version 1
    """
    without_block = _BLOCK_COMMENT.sub(" ", text)
    return without_block.split("//", 1)[0].strip()


## @brief One `#define` line as a (name, value) pair, or None when it is not one.
## @param line A single source line from a config header.
## @return (name, value) with an empty value for a bare define, else None.
## @version 1
## @dg_internal
def _define_from_line(line: str) -> tuple[str, str] | None:
    """SKIPS A CONTINUED MACRO ENTIRELY rather than truncating it. A value spanning
    lines with a trailing backslash cannot be read by a line-at-a-time scan, and half a
    value handed to doxygen as a whole one is a wrong answer wearing the shape of a
    right one — the failure class this repo keeps finding. A configuration macro is
    almost never continued; a code macro often is, and those are not what gh#17 asks us
    to feed through.

    SKIPS a value containing a double quote for the same reason: entries are quoted when
    emitted, so an embedded quote would break the Doxyfile line and change the meaning
    of every macro after it.

    @brief Parse an object-like `#define`, refusing what a line scan cannot read.
    @return (name, value), or None when the line is not a usable object-like define.
    @version 1
    """
    match = _DEFINE.match(line)
    if match is None or line.rstrip().endswith("\\"):
        return None
    value = _clean_value(match.group(2))
    return None if '"' in value else (match.group(1), value)


## @brief The bare NAMES of a set of rendered doxygen PREDEFINED tokens.
## @param tokens Rendered tokens — `'"NAME"'` or `'"NAME=value"'`, quoting included.
## @return The macro names, quoting and values stripped.
## @version 1
## @req REQ-DDB-CONFIG-004
def bare_macro_names(tokens: Iterable[str]) -> frozenset[str]:
    """ONE SPELLING FOR TWO STRING OPERATIONS, extracted because the second caller drifted on
    exactly one of them. `macros` holds already-rendered doxygen PREDEFINED tokens — the quoting
    is there because rendering the Doxyfile is what they were built for — so answering "is X
    defined" needs BOTH the quotes and any `=value` removed.

    `kconfig_gates` had its own version that removed the value and left the quotes, so
    `'"MBEDTLS_THREADING_C"' != 'MBEDTLS_THREADING_C'` and every declared macro was labelled
    `undeclared`: the `origin` field reported an entire configuration as absent from the build
    that declared it. Found by a control asking one build to distinguish a satisfied gate from an
    unsatisfied one; invisible to that function's own test, which fed it unquoted input.

    An empty result for an empty input is correct and not a fallback — a build that declares
    nothing defines nothing.

    @brief Reduce rendered PREDEFINED tokens to their names.
    @return Frozen set of names.
    @version 1
    """
    names = set()
    for token in tokens:
        bare = token.strip('"').split("=", 1)[0].strip()
        if bare:
            names.add(bare)
    return frozenset(names)


## @brief Harvest object-like `#define`s from a config header, honouring `#undef`.
## @param path Absolute path to the header to read.
## @return Macro entries as doxygen PREDEFINED tokens, in file order.
## @version 1
## @req REQ-DDB-CONFIG-004
def macros_from_header(path: Path) -> tuple[str, ...]:
    """A FLAT SCAN, not a preprocessor: `#if` blocks are walked through without being
    evaluated, so a define inside a conditional is harvested whether or not that
    conditional would hold. Stated rather than discovered — see the module docstring.
    It is the right trade for the job gh#17 names, because a config header states its
    configuration as top-level defines and comments out the alternatives, so a commented
    `//#define MBEDTLS_X` is correctly NOT harvested.

    `#undef` is honoured. A header that revokes a macro and is read as defining it would
    be worse than not reading the header at all.

    Unreadable degrades to empty WITH a warning rather than raising: the caller has
    already been told the file exists, and failing an index build over a metadata read
    would take a whole doxygen run with it.

    @brief Read a config header's object-like defines as PREDEFINED tokens.
    @return Ordered, deduplicated macro tokens.
    @version 1
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("preprocessor: %s is unreadable (%s) — no macros harvested", path, exc)
        return ()
    defined: dict[str, str] = {}
    for line in text.splitlines():
        undef = _UNDEF.match(line)
        if undef is not None:
            defined.pop(undef.group(1), None)
            continue
        parsed = _define_from_line(line)
        if parsed is not None:
            defined[parsed[0]] = parsed[1]
    return tuple(_token(name, value) for name, value in defined.items())


## @brief One macro rendered as a quoted doxygen PREDEFINED token.
## @param name Macro name.
## @param value Macro value, empty for a bare define.
## @return A quoted `"NAME"` or `"NAME=value"` token.
## @version 1
## @dg_internal
def _token(name: str, value: str) -> str:
    """QUOTED ALWAYS. Doxygen splits a PREDEFINED list on whitespace, so an unquoted
    `SIZE=1 + 2` becomes three entries — two of them nonsense macros. Quoting every
    token, not only the ones that need it, means the emitted line cannot depend on
    whether a value happened to contain a space.

    @brief Render a macro as a doxygen PREDEFINED token.
    @return The quoted token.
    @version 1
    """
    return f'"{name}={value}"' if value else f'"{name}"'


## @brief Locate a generated config header among conventional locations, refusing to guess.
## @param repo_root Resolved repo root to search.
## @return (path or None, the locations tried).
## @version 1
## @dg_internal
def _discover_config_header(repo_root: Path) -> tuple[Path | None, tuple[str, ...]]:
    """REFUSES ON AMBIGUITY, following `precommit._guard_config_conventional` and
    `doxygen.discover_doxyfile` for the reason both record: the latter once resolved
    strays alphabetically and was caught selecting a TEST FIXTURE's Doxyfile to index a
    whole project. Here the wrong choice is worse than that precedent, because it does
    not merely index the wrong files — it indexes a DIFFERENT VARIANT of the right ones,
    and every count taken from the result looks legitimate.

    The fallback (no macros, and every location named) is a known quantity, so guessing
    buys nothing.

    @brief Find a conventionally-placed generated config header, or refuse.
    @return (path or None, search locations).
    @version 1
    """
    searched = tuple(str(Path(name)) for name in _CONVENTIONAL_HEADERS)
    found = [p for name in _CONVENTIONAL_HEADERS if (p := repo_root / name).is_file()]
    if len(found) == 1:
        return found[0], searched
    if found:
        logger.warning(
            "preprocessor: config_header: %s found %d candidates (%s) and is NOT guessing "
            "which configuration this index should represent — name one explicitly",
            CONFIG_HEADER_AUTO,
            len(found),
            ", ".join(str(p.relative_to(repo_root)) for p in found),
        )
    else:
        logger.warning(
            "preprocessor: config_header: %s found none — searched %s. A generated config "
            "header does not exist until a build runs, so this index represents the "
            "UNCONFIGURED variant",
            CONFIG_HEADER_AUTO,
            ", ".join(searched),
        )
    return None, searched


## @brief Resolve the declared `config_header` to a path, whether named or discovered.
## @param repo_root Resolved repo root.
## @param declared The section's `config_header` value, or None.
## @return (path or None, the locations tried).
## @version 1
## @dg_internal
def _resolve_config_header(
    repo_root: Path, declared: object
) -> tuple[Path | None, tuple[str, ...]]:
    """A NAMED path is honoured even under a test directory: naming a mock config header
    is a deliberate statement about which variant an index should represent, and
    `preprocessor.config_header` records it for anyone reading the result. Only
    DISCOVERY refuses to go there, because discovery is where nobody chose.

    The named-but-missing case lives in `_named_config_header`, which this delegates to.

    @brief Turn a declared config_header value into a path.
    @return (path or None, search locations).
    @version 1
    """
    if not isinstance(declared, str) or not declared:
        return None, ()
    if declared == CONFIG_HEADER_AUTO:
        return _discover_config_header(repo_root)
    return _named_config_header(repo_root, declared)


## @brief Resolve an explicitly named config header, warning when it is missing.
## @param repo_root Resolved repo root.
## @param declared The repo-relative path the declaration names.
## @return (path or None, the declared location).
## @version 1
## @dg_internal
def _named_config_header(repo_root: Path, declared: str) -> tuple[Path | None, tuple[str, ...]]:
    """Split out of `_resolve_config_header` to keep both inside the max-3-returns
    standard, which caught the combined version at four.

    A named-but-missing path WARNS rather than failing the build, matching
    `declaration.declared_path` — and `preprocessor.source` still records that a
    configuration was declared, so the resulting zero macro count stays attributable to
    the typo instead of reading as "the owner declared nothing".

    @brief Resolve a named config header path.
    @return (path or None, the declared location).
    @version 1
    """
    path = (repo_root / declared).resolve()
    if not path.is_file():
        logger.warning(
            "preprocessor: config_header names %s, which does not exist — this index "
            "represents the UNCONFIGURED variant",
            declared,
        )
        return None, (declared,)
    return path, (declared,)


## @brief Merge two macro token lists, letting the first win by macro name.
## @param primary Tokens that win a name collision.
## @param secondary Tokens contributed second.
## @return Merged tokens, primary first, one per macro name.
## @version 1
## @dg_internal
def _merged(primary: tuple[str, ...], secondary: tuple[str, ...]) -> tuple[str, ...]:
    """AN EXPLICIT `predefined:` ENTRY BEATS A SCRAPED ONE. Doxygen's own behaviour on a
    duplicated PREDEFINED name is not something to rely on, so the collision is resolved
    here where the rule can be stated: the owner typed one of these by hand and the other
    was read out of a file, so the hand-typed one is the declaration.

    @brief Merge macro tokens, first list winning collisions.
    @return Merged token tuple.
    @version 1
    """
    seen = {token.split("=", 1)[0].strip('"') for token in primary}
    extra = tuple(t for t in secondary if t.split("=", 1)[0].strip('"') not in seen)
    return primary + extra


## @brief The macro list a section's `predefined:` key declares.
## @param section The parsed `preprocessor:` section.
## @return Quoted PREDEFINED tokens, or () when the key is absent or malformed.
## @version 1
## @dg_internal
def _declared_macros(section: dict[str, Any]) -> tuple[str, ...]:
    """Accepts entries either bare (`MBEDTLS_SSL_TLS_C`) or valued
    (`MBEDTLS_MAX_BLOCK_LENGTH=16`), and re-quotes both through `_token` so an author
    cannot produce a Doxyfile line that depends on their own quoting.

    A non-list value is ignored with a warning rather than coerced — a string here would
    otherwise be iterated CHARACTER BY CHARACTER into a hundred one-letter macros.

    @brief Read the declared macro list.
    @return Quoted tokens.
    @version 1
    """
    value = section.get(KEY_PREDEFINED)
    if value is None:
        return ()
    if not isinstance(value, list):
        logger.warning("preprocessor: %s must be a list of macros — ignoring it", KEY_PREDEFINED)
        return ()
    names = [str(v).strip() for v in value if str(v).strip()]
    return tuple(_token(*(n.split("=", 1) if "=" in n else (n, ""))) for n in names)


## @brief Resolve the preprocessor configuration for a build: flag, else declaration.
## @param repo_root Repo root the declaration and any config header are relative to.
## @param declaration The repo's parsed declaration (from load_declaration).
## @param explicit An operator-supplied macro list that wins outright, or None.
## @return The resolved PreprocessorConfig; an empty one when nothing was declared.
## @version 4
## @req REQ-DDB-CONFIG-004
def resolve_preprocessor(
    repo_root: Path | str | None,
    declaration: dict[str, Any] | None,
    explicit: list[str] | None = None,
) -> PreprocessorConfig:
    """An explicit `--predefined` WINS OUTRIGHT and does not merge, matching
    `_entry_patterns`' rule for a flag that replaces a list: the declaration is the
    repo's standing statement about which variant it ships, and an operator passing a
    macro list is deliberately indexing a different one. Merging would produce a third
    configuration nobody asked for.

    Reachable from BOTH entry points with nothing passed, because it works from
    `repo_root` and the declaration alone. That is the point rather than a convenience —
    CLAUDE.md's rule is that a declaration reachable only from argv is not a
    declaration, and the MCP build passes no override arguments.

    Returns an all-empty config when nothing is declared, which is what makes this
    change byte-identical to the previous behaviour for every existing target: no
    `PREDEFINED` line is emitted, no `build_meta` row is written, and the Doxyfile
    doxygen receives is unchanged.

    @brief Resolve the build's preprocessor configuration with its provenance.
    @return The resolved configuration.
    @version 4
    """
    section = (declaration or {}).get(SECTION_PREPROCESSOR)
    if explicit:
        ## THE MACRO LIST IS REPLACED; THE REPOSITORY'S OWN HEADER IS NOT A MACRO LIST. This branch
        ## used to `return` before reading `section` at all, so a declaration stating
        ## `config_header:` beside `predefined:` had that header silently discarded the moment a
        ## flag was passed — and `clew/cli.py` promotes a declared `predefined:` to this very
        ## `explicit` argument, so the acceptance build discarded its own declared header on every
        ## run. An accepted-but-unread key is this project's most repeated defect; this was one.
        ##
        ## What the flag legitimately overrides is WHICH VARIANT gets indexed. Where the repository
        ## states its own default is a fact ABOUT THE REPOSITORY and survives the override, which
        ## is what lets `stated_only` be computed: the overridden names the header does NOT define
        ## are exactly the ones that ship OFF.
        macros = tuple(_token(*(m.split("=", 1) if "=" in m else (m, ""))) for m in explicit)
        header, searched = (
            _resolve_config_header(
                Path(repo_root).expanduser().resolve(), section.get(KEY_CONFIG_HEADER)
            )
            if repo_root is not None and isinstance(section, dict) and section
            else (None, ())
        )
        root = Path(repo_root).expanduser().resolve() if repo_root is not None else None
        harvested = macros_from_header(header) if header is not None else ()
        return PreprocessorConfig(
            macros=macros,
            source=SOURCE_FLAG,
            config_header=str(header.relative_to(root)) if header is not None and root else None,
            searched=searched,
            ## Computed against the OVERRIDDEN list, not the declared one: the question a reader
            ## has is "of the macros this index was built with, which does the repo not ship?"
            ## `_stated_only` bare-names both sides itself, so the rendered tokens go in as-is.
            stated_only=_stated_only(macros, harvested),
        )
    if repo_root is None or not isinstance(section, dict) or not section:
        return PreprocessorConfig()
    root = Path(repo_root).expanduser().resolve()
    declared = _declared_macros(section)
    header, searched = _resolve_config_header(root, section.get(KEY_CONFIG_HEADER))
    harvested = macros_from_header(header) if header is not None else ()
    config = PreprocessorConfig(
        macros=_merged(declared, harvested),
        source=_source_of(section, declared, harvested),
        config_header=str(header.relative_to(root)) if header is not None else None,
        searched=searched,
        stated_only=_stated_only(declared, harvested),
    )
    ## Said out loud at INFO, because this decides WHICH VARIANT of the target gets
    ## indexed and every count downstream is relative to it. A resolution that produced
    ## nothing is the case most worth seeing, so it is logged too rather than skipped.
    logger.info(
        "preprocessor: %d macro(s) from %s%s",
        len(config.macros),
        config.source,
        f" ({config.config_header})" if config.config_header else "",
    )
    return config


## @brief The declared macro NAMES the repository's own config header does not define.
## @param declared Tokens from the `predefined:` key.
## @param harvested Tokens read from a config header.
## @return Bare names present in `declared` and absent from `harvested`, sorted.
## @version 1
## @req REQ-DDB-CONFIG-004
## @dg_internal
def _stated_only(declared: tuple[str, ...], harvested: tuple[str, ...]) -> tuple[str, ...]:
    """COMPARED BY BARE NAME, never by token. Both sides are rendered doxygen PREDEFINED tokens —
    `'"NAME"'` or `'"NAME=value"'` — so a token comparison would call `"X"` and `"X=1"` different
    macros and report a symbol as operator-only when the header defines it with a value. That is
    the exact drift `defined_names` was consolidated to prevent, and this is a third caller.

    EMPTY WHEN NO HEADER WAS READ, which is correct and not a degenerate case: with nothing
    harvested there is no statement about the repository's own defaults to make, so claiming every
    declared macro ships OFF would be inventing a fact. Absence stays absence.

    @brief Names stated by the operator and absent from the repo's config header.
    @return Sorted bare names.
    @version 1
    """
    if not harvested:
        return ()
    return tuple(sorted(bare_macro_names(declared) - bare_macro_names(harvested)))


## @brief Which sources contributed to a resolved configuration.
## @param section The parsed `preprocessor:` section.
## @param declared Tokens from the `predefined:` key.
## @param harvested Tokens read from a config header.
## @return One of the SOURCE_* provenance values.
## @version 1
## @dg_internal
def _source_of(
    section: dict[str, Any], declared: tuple[str, ...], harvested: tuple[str, ...]
) -> str:
    """Reads the SECTION, not only the results, so a declared-but-empty source is still
    attributed. A `config_header` that resolved to nothing must not report `declared`:
    the whole value of part 3 is that a zero macro count can be traced to the source that
    produced it.

    @brief Name the provenance of a resolved configuration.
    @return A SOURCE_* value.
    @version 1
    """
    has_declared = bool(declared) or KEY_PREDEFINED in section
    has_header = bool(harvested) or bool(section.get(KEY_CONFIG_HEADER))
    if has_declared and has_header:
        return SOURCE_BOTH
    return SOURCE_CONFIG_HEADER if has_header else SOURCE_DECLARED


## @brief The Doxyfile lines that supply a resolved configuration to doxygen.
## @param config The resolved preprocessor configuration.
## @return Doxyfile text to append, empty when no macros were resolved.
## @version 1
## @req REQ-DDB-CONFIG-004
def doxyfile_lines(config: PreprocessorConfig) -> str:
    """`PREDEFINED +=`, NEVER `PREDEFINED =`, and that is a correctness requirement
    rather than a style choice. Doxygen takes the last assignment to a key, so `=` here
    would silently DISCARD the `PREDEFINED` list a target's own Doxyfile declares —
    turning a feature that widens an index into one that narrows it for exactly the repos
    already doing the right thing. Appending means a declaration ADDS to the repo's own
    statement, and every existing target keeps building identically.

    `ENABLE_PREPROCESSING = YES` rides along because `PREDEFINED` has no effect without
    it. It is doxygen's default, so this is a no-op almost everywhere — but a repo that
    turned it off would otherwise get a declaration silently ignored, which is the
    reported-success-with-defaults failure the no-hardcoding mandate is about.
    `MACRO_EXPANSION` is deliberately NOT forced: it changes how bodies are parsed
    everywhere, not just which branches are taken, and gh#17 asks for the configuration
    to be supplied, not for the parse to be altered.

    One line per macro, so a diff of the hashed content names the macro that changed.

    @brief Render a resolved configuration as Doxyfile text.
    @return Text to append to the Doxyfile, or "" when there is nothing to supply.
    @version 1
    """
    if not config.macros:
        return ""
    lines = "".join(f"PREDEFINED += {token}\n" for token in config.macros)
    return f"\nENABLE_PREPROCESSING = YES\n{lines}"
