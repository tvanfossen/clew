# SPDX-License-Identifier: MIT
"""gh#11 — recover the function definitions doxygen never emitted.

tree-sitter already walks every indexed file on every build. On mbedtls's
`library/*.c` (108 files) doxygen yields **10** function bodies and tree-sitter
yields **2,507**, of which **2,495** sit in files doxygen reported as empty. Those
2,495 were parsed and then discarded, because `memberdef` is doxygen's own table
and the AST layers resolve their call-site endpoints to doxygen rowids: a function
doxygen never emitted cannot be an endpoint, so its parse contributed nothing.

Same shape as two defects this project has already fixed — scope provenance was
computed into a build LOG that was gone by query time, and the macro hop was
emitted by doxygen and never read. In all three the answer existed and the schema
had no place for it.

## What a recovered row is, and is not

A recovered row carries exactly what tree-sitter can see without a preprocessor:
`name`, the file, the body line span, the static-ness, the declarator's qualified
name (so `_common.qualified_name_of` can key its identity) and its parameter list.
It carries **no brief, no detailed description and therefore no `@req` tags**,
because a preprocessor that skipped the code skipped its doc comment too. Every
such row is stamped `dg_source='ast'` so a consumer can never read a missing brief
as an undocumented function when it is really an unparsed one.

**This does NOT replace declaring `PREDEFINED` (gh#17).** That recovers the
DOCUMENTATION; this recovers the GRAPH — symbols, bodies, call endpoints and the
richness layers built on them. They are complementary, not alternatives: where a
target can state its build configuration, stating it is strictly better, and where
it cannot, this is what stops the index from being silently empty. `coverage.py`
reports both ratios for exactly that reason.

## Python too, since gh#397 — and the reason it was excluded was measurably false

This section used to read: "The harvester refuses Python trees. doxygen indexes
Python fully — a Doxyfile-less Python codebase measured 4,739 functions — so there
is nothing to recover there, and a `function_definition` inside a Python `class`
would need scope handling this stage does not do."

Both halves were wrong by the time anyone checked.

**"doxygen indexes Python fully" is false.** On this repository's own index at build
42, `tests/test_mcp_server.py` declares 93 top-level functions and doxygen emitted
41. The other 52 were absent from every table — not truncated (rows reached the
file's last line), not misattributed (zero rows anywhere for sampled names), and
not predicted by whether a `##` doxygen block was present. The 4,739 figure was
never wrong about that one target; it was read as a guarantee about the language.
So the backstop for doxygen's misses stood switched off on the grounds that doxygen
does not miss, and `dg_source` counts across the whole self-index were `ast`=3
against `doxygen`=4,493.

**"scope handling this stage does not do" was true of this MODULE and false of the
package.** `pyast.class_ranges`/`enclosing_class` already answer "which class is
this inside", for the call-edge layer. `harvest_python_definitions` reuses them
rather than growing a second answer.

gh#11 remains a preprocessor defect and the preprocessor remains a C/C++
phenomenon — but the SYMPTOM it fixes, a parser seeing a definition the index does
not hold, is not exclusive to that cause. Enabling Python took that one file from
52 missing to 1 and the repo from 158 to 160 of 172 files holding >=95% of their
defs. Rebuilding mbedtls across the change left all 36 tables byte-identical, so
the widening is a strict no-op on C.

Only FUNCTIONS are recovered for Python. A module-level assignment is already
indexed by doxygen, and `harvest_variable_declarations` reads C declarator shapes
the Python grammar does not produce.

## How the duplicate is avoided, and in which direction it fails

A recovered row for a function doxygen ALREADY emitted would be a double count,
and that is the likeliest way this change goes wrong. Dedup is by **body-span
overlap within the file**, not by name:

  * By NAME would be wrong in the under-recovery direction only, but wrongly: two
    classes' `tick()` in one translation unit, one of them behind an unsatisfied
    `#if`, would skip the recoverable one because the name was already present.
  * By SPAN separates them, because two functions cannot occupy the same lines.

A parsed definition is dropped when its `[start, end]` overlaps ANY doxygen body
span in the same file. Ties and unreadable spans fail toward DROPPING the parsed
row: a missing symbol is a known limitation, while a duplicate corrupts every
count and every name resolution built on top of it.

## Global and file-scope VARIABLES, recovered by the same mechanism (gh#372)

The measured gap: mbedtls declares five global mutex OBJECTS
(`mbedtls_threading_readdir_mutex` and friends) behind `#if defined(MBEDTLS_FS_IO)`
/ `THREADING_USE_GMTIME` / `MBEDTLS_PSA_CRYPTO_C`, and its lock PRIMITIVE
(`mbedtls_mutex_lock`) is a function-POINTER global behind `MBEDTLS_THREADING_C`.
doxygen's preprocessor strips all six, so `search` for any of them returned a
confident zero and the only route to the repo's mutex list was reading a function
BODY. Establishing this took one query rather than a guess: doxygen's own sqlite
output holds 902 `kind='variable'` rows and `clew.db` holds the same 902, so the
importer filters nothing — the rows were never emitted. Those 902 are struct
members and Python class attributes; not one is a file-scope global.

Recovery is the SAME argument as for functions, one kind over: the parser reads
source text, so a preprocessor guard is not its problem.

**A recovered variable row is deliberately impoverished.** It carries `name`, its
declared type, the file, the line and its static-ness — and NO body span, NO
`bodyfile_id`, no brief and no callers or callees, because a variable has none of
those. `kind='variable'` (doxygen's own vocabulary value, so no schema change) is
what stops a consumer reading it as a function: every call, reachability, thread
and requirement layer already filters `kind='function'`, so a variable row cannot
become a graph endpoint. **No call edge is ever created to or from one** —
variable-mediated coupling is `shared_key_edges`'s job and has its own evidence
rules.

### The prototype/function-pointer discriminator, read off the grammar

A C `declaration` node covers three things this stage must tell apart, and the
shapes were PROBED rather than assumed:

    int some_prototype(int x);          function_declarator → identifier
    void (*mbedtls_mutex_lock)(...);    function_declarator → parenthesized_declarator
                                                            → pointer_declarator → identifier
    mbedtls_threading_mutex_t m;        identifier

The first is a function prototype and must NOT become a variable; the second is a
function-pointer variable and must. Both are `function_declarator`, so the
discriminator is the `parenthesized_declarator` — a prototype has none. That
distinction is exactly what the mbedtls question needs, because the mutex objects
and the lock primitive are different kinds of global and a reader has to separate
them.

Fail-closed choices, each one narrowing what gets recovered:

  * Only a bare `identifier` names a recovered variable. A `qualified_identifier`
    (`int Owner::s_count_ = 0;`, an out-of-line static member definition) is
    REFUSED, because doxygen already emits that member from its class body and a
    second row keyed to a different identity is gh#26 by another route.
  * The walk does not descend into a `function_definition`, so a function's LOCALS
    are never recovered, nor into a `field_declaration_list`, so C++ class members
    stay doxygen's alone. Neither does it descend into a `declaration` it accepted.
  * Dedup is by `(file, name)` across EVERY kind, not by span: a variable has no
    body to overlap, and C forbids two file-scope variables sharing a name in one
    file, so the pair is an exact identity here in a way it is not for functions.
    Matching any kind means a name the index already carries in that file is left
    alone rather than duplicated under a second kind.

## MACRO DEFINITIONS, INCLUDING THE BRANCH DOXYGEN NEVER SEES (gh#403)

The measured gap, and it is the same shape a third time. mbedtls answers its own
graded Q2 — "the same struct member has two different names; which, why, and who
gets which" — in six lines of `include/mbedtls/private_access.h`:

    #ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
    #define MBEDTLS_PRIVATE(member) private_##member    /* line 15 */
    #else
    #define MBEDTLS_PRIVATE(member) member              /* line 17 */
    #endif

**doxygen emits ONE of those two rows.** Its preprocessor evaluates the `#ifndef`,
takes the true branch and never reaches the `#else`, so the index held line 15 and
was structurally incapable of holding line 17 — half the answer, with nothing
saying a half was missing. The graded run measured the consequence: `dossier`
returned rows on every call and the agent read source **eight to nine times per
run** anyway, because the payload could not state the second spelling.

A `#define` is the LEAST preprocessor-dependent thing in a C file — its text is
right there — so the parser is again not blocked by what blocked doxygen. Recovery
mirrors the variable path: `kind='macro definition'` is doxygen's own vocabulary
value, `initializer` holds the expansion, and the parameter names go to
`param`/`memberdef_param` the way doxygen writes them, so `macro_definitions_conn`
reads a recovered site through exactly the query it already had.

**Dedup is by `(file, name, LINE)`, and the line is what makes the second branch
recoverable at all.** The two other keys in this module would both be wrong here:

  * By `(file, name)` — the variable rule — line 17 would be dropped, because
    doxygen already carries `MBEDTLS_PRIVATE` in that file. That is the defect.
  * By body-span overlap — the function rule — doxygen writes `bodystart` on a
    macro row (`bodystart=15, bodyend=-1` on the real one), so a span rule would
    compare against a half-open extent that means something else.

The line is an exact identity here because two `#define`s of one name cannot begin
on one line, and doxygen and tree-sitter AGREE on which line that is — verified on
the real header with `.claude/tmp/macro_shape_probe.py`, both reporting 15. Matching
across EVERY kind would reintroduce the original bug: `MBEDTLS_PRIVATE` is carried
~2,000 times as `kind='function'` (doxygen writes a row per wrapped struct field),
so a cross-kind NAME rule would skip the macro entirely, which is precisely how
gh#373 found the layer unreachable.

**A recovered macro row carries NO body span**, unlike doxygen's own. `bodystart`
feeds `_covered_body_spans`, which decides what function recovery may insert, and a
macro is not a function body; writing one would let a `#define` block a recoverable
definition and would inflate `graph_stats`'s "files with bodies" count with files
that only define macros.

`expansion` is the VERBATIM source text of the value, line continuations and all.
doxygen's `initializer` is likewise its own rendering of the same bytes; normalising
ours would make two rows of one macro differ by who recovered them.

@brief Recover parser-visible function definitions, globals and macros doxygen did not emit.
@version 3
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .harvest import Harvester, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .pyast import class_ranges, enclosing_class, is_python_tree, node_text

## IMPORTED, NOT RESPELLED. `'macro definition'` is doxygen's own vocabulary string and
## `query/macros.py` already owns the one copy, with a comment saying a second literal is
## "the drift that silently empties one caller while the other keeps working" — a writer and
## a reader of the same rows is exactly that pair. `query/` imports only stdlib and
## `vocabulary`, so this adds no dependency the pipeline did not already have
## (`dominated_edges` and `cli` both reach into `query._common` the same way).
from .query.macros import MACRO_KIND
from .vocabulary import (
    STAGE_AST_SYMBOLS,
    SYMBOL_SOURCE_AST,
    SYMBOL_SOURCE_COLUMN,
    SYMBOL_SOURCE_DOXYGEN,
    check,
)

__all__ = [
    "ParsedFunction",
    "ParsedMacro",
    "ParsedVariable",
    "ensure_symbol_provenance",
    "harvest_function_definitions",
    "harvest_macro_definitions",
    "harvest_variable_declarations",
    "recover_ast_symbols",
]

logger = logging.getLogger(__name__)

## The tree-sitter node type C and C++ both use for "a function with a body". A
## DECLARATION is a different node type, which is why parsing a header yields
## nothing here and no phantom body span is ever invented.
_FUNCTION_DEFINITION = "function_definition"

## The declarator name-node types whose text IS the function's name, enumerated by
## PROBING the C++ grammar rather than assumed — the first cut accepted only
## `identifier` and `qualified_identifier`, and that silently skipped EVERY in-class
## method definition, because tree-sitter-cpp names a member `field_identifier`.
## Nothing failed; those symbols were simply never recovered, and the gap only
## surfaced when a test asserted that an in-class method WAS recovered.
##
##   identifier            a free function, and a template function
##   field_identifier      a method defined inside its class body
##   qualified_identifier  an out-of-line definition — `Owner::acquire`, which is
##                         what `qualified_name_of` needs in order to key this row
##                         to the same identity as doxygen's declaration row
##   destructor_name       `~Owner`, which is also how doxygen names it
##
## An `operator=` is deliberately absent: its declarator is a `reference_declarator`
## with no `function_declarator` under it, so it is refused upstream and stays
## refused. Fail closed — a symbol whose name we cannot state is worse than none.
_NAME_NODES = ("identifier", "field_identifier", "qualified_identifier", "destructor_name")

## `static` in C/C++ is a `storage_class_specifier`. Read from the node rather than
## from the source text so a function named `static_helper` is not mistaken for one.
_STORAGE_CLASS = "storage_class_specifier"
_STATIC = "static"

## The tree-sitter node type C and C++ use for a non-function declaration at file
## scope. It ALSO covers function prototypes and a function's own locals, which is
## why `_declared_variable_name` refuses one and the walk never enters the other.
_DECLARATION = "declaration"

## Node types the walk refuses to enter when looking for file-scope variables.
## `function_definition` keeps a function's LOCALS out — they are not globals and
## recovering them would flood the index with `i`, `ret` and `len`.
## `field_declaration_list` keeps C++ class members out; doxygen emits those from the
## class body already, and tree-sitter names them `field_declaration` rather than
## `declaration`, so this is belt-and-braces on a boundary that matters.
_VARIABLE_WALK_SKIPS = (_FUNCTION_DEFINITION, "field_declaration_list")

## Declarator wrappers to unwrap on the way from a `declaration`'s declarator field
## down to the name. Enumerated by PROBING the C grammar, same discipline as
## `_NAME_NODES`:
##
##   init_declarator          `names[] = {...}` — an initialiser is present
##   pointer_declarator       `*names`
##   array_declarator         `names[]`
##   reference_declarator     `&ref` (C++)
##   parenthesized_declarator `(*fn)` — the function-POINTER marker, see below
##   function_declarator      `fn(int)` — a prototype UNLESS parenthesized
_DECLARATOR_WRAPPERS = (
    "init_declarator",
    "pointer_declarator",
    "array_declarator",
    "reference_declarator",
    "parenthesized_declarator",
    "function_declarator",
)

## A `parenthesized_declarator` carries its inner declarator as an unnamed child
## between the parentheses rather than in a `declarator` FIELD, so
## `child_by_field_name` returns None on it and the unwrap chain would stop dead one
## node above the name. Probed, not assumed: its children are `(`, the inner
## declarator, `)`, and only the middle one is NAMED.
_PARENTHESIZED = "parenthesized_declarator"
_FUNCTION_DECLARATOR = "function_declarator"

## Hard cap on declarator unwrap depth. A real declaration nests three or four deep;
## the cap exists so a pathological or error-recovered tree cannot spin here.
_MAX_DECLARATOR_DEPTH = 16


## @brief One function definition tree-sitter found in one file.
## @version 1
@dataclass(frozen=True)
class ParsedFunction:
    """A function definition as the parser sees it: its bare name, the qualified
    name its declarator spelled (equal to `name` when the source did not qualify
    it), its parameter list text, whether it is `static`, and its body line span.

    Rowid-FREE by construction, which is what makes it cacheable — see
    `harvest.Harvester`. doxygen reassigns `memberdef.rowid` on every run, so a
    cached payload may only record source text and line numbers.

    @brief One parser-visible function definition (name + span + static-ness).
    @version 1
    """

    name: str
    qualified: str
    args: str
    static: bool
    start: int
    end: int

    ## @brief True when this definition's body overlaps a given line span.
    ## @param other_start First line of the other span.
    ## @param other_end Last line of the other span.
    ## @return True when the two closed intervals share at least one line.
    ## @version 1
    ## @req REQ-DDB-INDEX-004
    def overlaps(self, other_start: int, other_end: int) -> bool:
        """Closed-interval overlap on both ends: doxygen's `bodystart` is the
        signature line and its `bodyend` the closing brace, and tree-sitter's
        `function_definition` span covers the same extent, so a genuine match
        overlaps heavily rather than merely touching. A single shared line is
        still treated as a match because the failure direction is deliberate —
        dropping a real symbol is a known limitation, duplicating one is not.

        An `other_end` below `other_start` (doxygen records `-1` for a body it
        never saw closed) collapses to the single line `other_start`, so a
        malformed span cannot match everything after it.

        @brief Do this definition's lines intersect the given span?
        @return True on any shared line.
        @version 1
        """
        end = max(other_end, other_start)
        return self.start <= end and other_start <= self.end


## @brief One file-scope variable declaration tree-sitter found in one file.
## @version 1
@dataclass(frozen=True)
class ParsedVariable:
    """A global or file-scope variable as the parser sees it: its name, the declared
    type text, whether it is `static`, and the line it is declared on.

    HAS NO BODY SPAN, and that absence is the point. A variable is not executable, so
    there is nothing for `_covered_body_spans` to compare and nothing for a caller to
    trace into. `ParsedFunction` carries `start`/`end` because a function body has
    them; inventing a span here would put a variable into the one dedup mechanism it
    does not belong in, and would make `graph_stats`'s "files with bodies" count it.

    Rowid-FREE by construction like `ParsedFunction`, for the same cache reason.

    @brief One parser-visible file-scope variable (name + type + line).
    @version 1
    """

    name: str
    type_text: str
    declarator_text: str
    static: bool
    line: int

    ## @brief doxygen's own `definition` spelling for this variable.
    ## @return "<type> <declarator>", or just the name when neither is available.
    ## @version 2
    ## @req REQ-DDB-INDEX-004
    def definition(self) -> str:
        """Matches the convention doxygen already uses for its own variable rows —
        one reads `size_t mbedtls_ecp_group::nbits` and another
        `FStar_UInt128_uint128(* FStar_UInt128_op_Plus_Hat) (...)` — so a consumer
        reading `definition` gets the same shape whichever provenance the row has.
        Read off a real index rather than invented, because a second spelling for one
        column is what makes a caller write two parsers.

        THE DECLARATOR, NOT THE BARE NAME, and this was a measured correction. A C
        `declaration`'s `type` field holds only the BASE type: for
        `int (*mbedtls_mutex_lock)(mbedtls_threading_mutex_t *)` it is just `int`, with
        the pointer-to-function part living in the declarator. Building the definition
        from the name alone therefore published mbedtls's lock PRIMITIVE as
        `int mbedtls_mutex_lock` — indistinguishable from an integer counter, on the
        one row whose whole value is telling a reader it is a function pointer rather
        than a mutex object. Confirmed on the built index before the fix.

        @brief Render the type-and-declarator definition string.
        @return The definition text.
        @version 2
        """
        return f"{self.type_text} {self.declarator_text or self.name}".strip()


## @brief The `static` storage class on a function_definition node.
## @param node A `function_definition` node.
## @param src_bytes The file's raw bytes.
## @return True when one of the node's children is the `static` storage class.
## @version 1
## @dg_internal
def _is_static(node: Any, src_bytes: bytes) -> bool:
    """@brief Detect a `static` function definition.

    @return True for a static function.
    @version 1
    """
    return any(
        child.type == _STORAGE_CLASS and node_text(child, src_bytes).strip() == _STATIC
        for child in node.children
    )


## @brief The declarator's name node, unwrapping pointer/parenthesized declarators.
## @param node A `function_definition` node.
## @return The `function_declarator` node, or None when the shape is not one.
## @version 1
## @dg_internal
def _function_declarator(node: Any) -> Any | None:
    """A pointer-returning definition nests the declarator
    (`Slot* Owner::acquire()` puts the sigil INSIDE the declarator, which is the
    same shape that split entropic's lock scopes), so unwrap until a
    `function_declarator` is reached or the chain runs out.

    @brief Find the `function_declarator` under a definition node.
    @return The declarator node, or None.
    @version 1
    """
    current = node.child_by_field_name("declarator")
    while current is not None and current.type != "function_declarator":
        current = current.child_by_field_name("declarator")
    return current


## @brief Bare and qualified names for one function declarator.
## @param declarator A `function_declarator` node.
## @param src_bytes The file's raw bytes.
## @return (bare name, qualified name), or None when no static name is identifiable.
## @version 3
## @dg_internal
def _declared_names(declarator: Any, src_bytes: bytes) -> tuple[str, str] | None:
    """Refuses anything that is not a plain `identifier` or a `qualified_identifier`
    — an `operator_name`, a `destructor_name`, or a declarator doxygen would have
    mis-parsed from a macro. Fail closed: a row whose name we cannot state is worse
    than an absent row, because every downstream name resolution would inherit the
    guess.

    Written as one table-driven exit rather than a chain of returns: the house
    limit is three, and a per-node-type chain over `_NAME_NODES` would be five. The
    `rsplit` is a no-op for every unqualified form, so one expression serves all
    four.

    @brief Extract a declarator's bare and qualified names.
    @return (bare, qualified) or None.
    @version 3
    """
    name_node = declarator.child_by_field_name("declarator")
    if name_node is None or name_node.type not in _NAME_NODES:
        return None
    qualified = node_text(name_node, src_bytes)
    return qualified.rsplit("::", 1)[-1], qualified


## @brief Build a ParsedFunction from one function_definition node.
## @param node A `function_definition` node.
## @param src_bytes The file's raw bytes.
## @return The ParsedFunction, or None when the node has no body or no usable name.
## @version 2
## @dg_internal
def _parsed_function(node: Any, src_bytes: bytes) -> ParsedFunction | None:
    """REQUIRES AN ACTUAL BODY, and this was found by measurement rather than by
    reading the grammar. `W(W&&) = default;` and `W(const W&) = delete;` are
    `function_definition` nodes in tree-sitter-cpp — the `= default;` sits where a
    body would — so recovering them produced a row for a member that HAS no body,
    and doxygen had already emitted a declaration row for it. Measured on entropic:
    18 of 20 recovered rows were defaulted or deleted special members, each one a
    second row for a function doxygen already knew, and because their `definition`
    is the bare declarator they keyed to a DIFFERENT `qualified_name_of` identity
    than doxygen's `entropic::SandboxManager::SandboxManager` — two graph nodes for
    one function, which is gh#26 reintroduced.

    The discriminator is the grammar's own: a real definition has a `body` field
    holding a `compound_statement`, while a defaulted/deleted member has `body =
    None`. Tested rather than pattern-matched against `default_method_clause` /
    `delete_method_clause` by name, so anything else the grammar shapes without a
    body is excluded too.

    @brief Convert one definition node into its rowid-free record.
    @return ParsedFunction, or None for a bodiless node or an unusable name.
    @version 2
    """
    if node.child_by_field_name("body") is None:
        return None
    declarator = _function_declarator(node)
    names = _declared_names(declarator, src_bytes) if declarator is not None else None
    if names is None:
        return None
    params = declarator.child_by_field_name("parameters")
    return ParsedFunction(
        name=names[0],
        qualified=names[1],
        args=node_text(params, src_bytes) if params is not None else "()",
        static=_is_static(node, src_bytes),
        start=node.start_point[0] + 1,
        end=node.end_point[0] + 1,
    )


## @brief Every top-level function definition in one parsed C/C++ tree.
## @param tree The parsed tree.
## @param src_bytes The file's raw bytes.
## @return ParsedFunction records in document order.
## @version 1
## @req REQ-DDB-INDEX-004
def harvest_function_definitions(tree: Any, src_bytes: bytes) -> list[ParsedFunction]:
    """Does NOT descend into a definition once one is found. A function nested
    inside another (a GNU nested function, or a lambda the grammar happened to
    shape as a definition) would otherwise be recorded as a second symbol whose
    span sits INSIDE its parent's — and the span-overlap dedup would then reject
    whichever of the two it saw second, making the outcome order-dependent.

    Class and namespace bodies ARE descended into, because a method defined
    in-class is a top-level symbol as far as this stage is concerned.

    @brief Collect a C/C++ file's function definitions.
    @return ParsedFunction records.
    @version 1
    """
    found: list[ParsedFunction] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type != _FUNCTION_DEFINITION:
            stack.extend(reversed(node.children))
            continue
        parsed = _parsed_function(node, src_bytes)
        if parsed is not None:
            found.append(parsed)
    return found


## @brief Step one link down a declarator chain, handling the parenthesized shape.
## @param node A declarator node being unwrapped.
## @return The next declarator down, or None at the end of the chain.
## @version 1
## @dg_internal
def _next_declarator(node: Any) -> Any | None:
    """`child_by_field_name('declarator')` reaches the next link for every wrapper
    EXCEPT `parenthesized_declarator`, which holds its inner declarator as an unnamed
    child between the parentheses. Probed: its children are `(`, the inner declarator,
    `)`, and only the middle is NAMED — so the first named child is the link.

    Without this the chain for `void (*mbedtls_mutex_lock)(...)` stops at the
    parenthesis and the name is never reached, which would silently drop exactly the
    function-pointer globals this change exists to index. A silent drop, because the
    node simply looks like the end of a chain.

    @brief Descend one declarator link.
    @return The next declarator, or None.
    @version 1
    """
    field = node.child_by_field_name("declarator")
    if field is not None or node.type != _PARENTHESIZED:
        return field
    named = [child for child in node.children if child.is_named]
    return named[0] if named else None


## @brief The identifier a declaration declares, refusing function prototypes.
## @param declarator One `declarator`-field child of a `declaration` node.
## @return The `identifier` node naming a variable, or None when this is not one.
## @version 1
## @dg_internal
def _declared_variable_name(declarator: Any) -> Any | None:
    """THE PROTOTYPE/FUNCTION-POINTER DISCRIMINATOR LIVES HERE, and it is the one
    judgement in this stage that a wrong answer makes actively harmful rather than
    merely incomplete — a function prototype recorded as a variable is precisely the
    "a variable appearing where a caller expected a function" failure.

    Both shapes present a `function_declarator`, so that node cannot decide it:

        int some_prototype(int x);     function_declarator → identifier
        void (*mbedtls_mutex_lock)();  function_declarator → parenthesized_declarator
                                                           → pointer_declarator → identifier

    The `parenthesized_declarator` is the discriminator — C requires the parentheses
    to bind the `*` to the name rather than the return type, so a function-pointer
    VARIABLE always has one and a prototype never does. Read off the grammar by
    probing both spellings, not inferred from the source text.

    Refuses anything whose chain does not end in a bare `identifier`: a
    `qualified_identifier` is an out-of-line static member definition doxygen already
    emitted from the class body, and recovering it would key a second row to a
    different identity. Fail closed, same rule as `_declared_names`.

    @brief Extract a variable declaration's name node.
    @return The `identifier` node, or None for a prototype or unusable shape.
    @version 1
    """
    current: Any | None = declarator
    saw_function = False
    saw_parenthesized = False
    for _ in range(_MAX_DECLARATOR_DEPTH):
        if current is None or current.type not in _DECLARATOR_WRAPPERS:
            break
        saw_function = saw_function or current.type == _FUNCTION_DECLARATOR
        saw_parenthesized = saw_parenthesized or current.type == _PARENTHESIZED
        current = _next_declarator(current)
    unusable = current is None or current.type != "identifier"
    return None if unusable or (saw_function and not saw_parenthesized) else current


## @brief Every variable one `declaration` node declares.
## @param node A `declaration` node.
## @param src_bytes The file's raw bytes.
## @return ParsedVariable records, one per declared name.
## @version 1
## @dg_internal
def _parsed_variables(node: Any, src_bytes: bytes) -> list[ParsedVariable]:
    """ONE DECLARATION CAN DECLARE SEVERAL NAMES. `int multi_a, multi_b;` gives the
    node TWO `declarator`-field children, so reading `child_by_field_name` — singular
    — would have indexed the first and silently dropped every one after it. Probed:
    `children_by_field_name` returns both. The type text and the storage class are
    properties of the declaration and are therefore shared by all of its names.

    @brief Extract every variable a declaration declares.
    @return One record per usable declared name.
    @version 1
    """
    type_node = node.child_by_field_name("type")
    type_text = node_text(type_node, src_bytes).strip() if type_node is not None else ""
    static = _is_static(node, src_bytes)
    line = node.start_point[0] + 1
    found: list[ParsedVariable] = []
    for declarator in node.children_by_field_name("declarator"):
        name_node = _declared_variable_name(declarator)
        if name_node is not None:
            found.append(
                ParsedVariable(
                    name=node_text(name_node, src_bytes),
                    type_text=type_text,
                    declarator_text=_declarator_text(declarator, src_bytes),
                    static=static,
                    line=line,
                )
            )
    return found


## @brief The declarator's source text, with any initialiser stripped.
## @param declarator One `declarator`-field child of a `declaration` node.
## @param src_bytes The file's raw bytes.
## @return The declarator text without its `= value` tail.
## @version 1
## @dg_internal
def _declarator_text(declarator: Any, src_bytes: bytes) -> str:
    """STRIPS THE INITIALISER by descending through an `init_declarator` to its own
    declarator field, rather than by cutting the text at the first `=`. A textual cut
    would mangle `int a[] = {1, 2}` and would be defeated outright by an `=` inside a
    template argument or a string literal; the grammar already separates the two, so
    the node is the honest place to read it.

    Falls back to the whole node's text when the shape is unexpected, which keeps a
    surprising declarator informative rather than blank — this feeds a display column,
    never an identity, so a slightly-too-long string costs nothing while an empty one
    loses the pointer-to-function spelling that is the reason this exists.

    @brief Render a declarator's text without its initialiser.
    @return The declarator source text.
    @version 1
    """
    node = declarator
    if node.type == "init_declarator":
        node = node.child_by_field_name("declarator") or declarator
    return node_text(node, src_bytes).strip()


## @brief Every file-scope variable declaration in one parsed C/C++ tree.
## @param tree The parsed tree.
## @param src_bytes The file's raw bytes.
## @return ParsedVariable records in document order.
## @version 1
## @req REQ-DDB-INDEX-004
def harvest_variable_declarations(tree: Any, src_bytes: bytes) -> list[ParsedVariable]:
    """Skips `function_definition` and `field_declaration_list` subtrees entirely, so
    a function's locals and a C++ class's members are never reached — the two ways a
    `declaration` node can be something other than a global. It also does not descend
    into a `declaration` it has already read, so a declaration nested inside another
    cannot produce a second record for the same name.

    A `declaration` inside a `preproc_if` IS reached, and that is the whole point:
    mbedtls's five global mutexes sit under `#if defined(MBEDTLS_FS_IO)` and friends,
    which is why doxygen never emitted them. Verified by probe — tree-sitter shapes
    them as `translation_unit → preproc_if → declaration`.

    @brief Collect a C/C++ file's file-scope variable declarations.
    @return ParsedVariable records.
    @version 1
    """
    found: list[ParsedVariable] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in _VARIABLE_WALK_SKIPS:
            continue
        if node.type != _DECLARATION:
            stack.extend(reversed(node.children))
            continue
        found.extend(_parsed_variables(node, src_bytes))
    return found


## A C/C++ `typedef`. tree-sitter shapes `typedef struct X { ... } X;` as a
## `type_definition` wrapping a `struct_specifier`, and PROBING mbedtls's real
## `include/mbedtls/threading.h` is how that was established rather than assumed:
## the definition sits at `type_definition` lines 29-39 with the `struct_specifier`
## at the same span.
_TYPE_DEFINITION = "type_definition"

## The declarator field on a `type_definition` carries the NAME the typedef introduces.
_TYPE_IDENTIFIER = "type_identifier"


## @brief A C/C++ file's typedef names, including ones behind unsatisfied guards.
## @param tree Parsed C/C++ tree.
## @param src_bytes The file's raw bytes.
## @return ParsedVariable records carrying the typedef name and its underlying text.
## @version 1
## @req REQ-DDB-PIPE-003
def harvest_type_definitions(tree: Any, src_bytes: bytes) -> list[ParsedVariable]:
    """gh#395, and it is gh#11 one kind over. The MEASURED gap:
    `dossier("mbedtls_threading_mutex_t")` returns the alt-dummy at
    `tests/include/alt-dummy/threading_alt.h` — a `struct { int dummy; }` — while the real
    pthread-backed type at `include/mbedtls/threading.h:29` produces NO ROW IN ANY TABLE,
    because it sits behind `MBEDTLS_THREADING_PTHREAD`. Exactly one `compounddef` row exists
    for that name, so resolution picked the only row available and was right to.

    THAT IS WHY IT WAS NEARLY MISFILED AS A RANKING BUG. A test-path demotion tier would
    have produced a green test proving a demotion worked while the real type stayed
    invisible. "No rows" is a claim about the detector until you read the source.

    REUSES `ParsedVariable`, which is the honest shape: a typedef has a name, a declared
    text and a line, and NO BODY SPAN — the same three facts, and the same absence, that
    type already models for a variable. Recovered as `kind='typedef'`, which is doxygen's
    OWN vocabulary value and already in `SEARCHED_MEMBERDEF_KINDS`, so the recovered type
    becomes findable with no schema change and no new enum.

    MEMBERS ARE NOT RECOVERED HERE, deliberately and it is a real limitation. mbedtls
    declares them as `pthread_mutex_t MBEDTLS_PRIVATE(mutex)` — the member names are wrapped
    in a MACRO, which is the same blindness this project has recorded three times, and
    unwrapping it correctly is Q2's own subject rather than a detail of this walk. Members
    need `compounddef` + `member` writes; this gives existence, kind, file and line.

    Skips the same subtrees as the variable walk: a typedef inside a function body or a
    class member list is not a file-scope type.

    @brief Collect a C/C++ file's typedef definitions.
    @return ParsedVariable records.
    @version 1
    """
    found: list[ParsedVariable] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in _VARIABLE_WALK_SKIPS:
            continue
        if node.type != _TYPE_DEFINITION:
            stack.extend(reversed(node.children))
            continue
        parsed = _parsed_typedef(node, src_bytes)
        if parsed is not None:
            found.append(parsed)
    return found


## @brief Build a ParsedVariable from one `type_definition` node.
## @param node A `type_definition` node.
## @param src_bytes The file's raw bytes.
## @return ParsedVariable, or None when no name can be read.
## @version 1
## @dg_internal
def _parsed_typedef(node: Any, src_bytes: bytes) -> ParsedVariable | None:
    """Reads the LAST `type_identifier` child, because that is where the introduced name
    sits: `typedef struct mbedtls_threading_mutex_t { ... } mbedtls_threading_mutex_t;` has
    a `type_identifier` inside the `struct_specifier` (the struct TAG) and another as the
    declarator (the typedef NAME). They are equal here and are NOT in general —
    `typedef struct foo_s foo_t;` differs — and it is the declarator that a caller types.

    Fail closed: a `type_definition` whose declarator is a function-pointer or array shape
    yields no bare `type_identifier`, and returning None leaves it out rather than recording
    a name this walk cannot state.

    @brief Parse one typedef into a ParsedVariable.
    @return ParsedVariable or None.
    @version 1
    """
    names = [c for c in node.children if c.type == _TYPE_IDENTIFIER]
    if not names:
        return None
    name = node_text(names[-1], src_bytes)
    if not name:
        return None
    return ParsedVariable(
        name=name,
        type_text="typedef",
        declarator_text=name,
        static=False,
        line=node.start_point[0] + 1,
    )


## The two tree-sitter nodes a `#define` produces. BOTH are needed and the
## function-like one is the case that matters: `MBEDTLS_PRIVATE(member)` is a
## `preproc_function_def`, and a walk that accepted only `preproc_def` would recover
## every object-like `#define` in the repository and miss the one symbol gh#403 exists
## for. Probed on the real header with `.claude/tmp/macro_shape_probe.py`, which
## reported `preproc_def` for the include guard at line 12 and
## `preproc_function_def` at 15 and 17.
_PREPROC_DEF = "preproc_def"
_PREPROC_FUNCTION_DEF = "preproc_function_def"
_MACRO_DEF_NODES = (_PREPROC_DEF, _PREPROC_FUNCTION_DEF)

## The grammar's field names on those nodes. `value` is OPTIONAL — `#define FOO_H`
## with no expansion is the include-guard idiom and yields None — and reading its
## absence as an empty expansion is correct rather than a fallback: doxygen stores ''
## for the same thing.
_FIELD_NAME = "name"
_FIELD_VALUE = "value"
_FIELD_PARAMETERS = "parameters"

## A `preproc_params` node's children are `(`, the parameter identifiers, `,` and `)`.
## Only these two types are parameters; taking every child would put the punctuation
## in the parameter list. `...` is C99's variadic marker and IS a parameter — a macro
## declaring one is variadic, and dropping it would report `#define LOG(fmt, ...)` as
## taking one argument.
_PARAM_NODES = ("identifier", "...")


## @brief One preprocessor definition tree-sitter found in one file.
## @version 1
@dataclass(frozen=True)
class ParsedMacro:
    """A `#define` as the parser sees it, which is very nearly all there is to see: a
    name, an optional parameter list, the replacement text and the line it starts on.

    A SEPARATE TYPE FROM `ParsedVariable`, which the typedef path reuses. A typedef
    genuinely IS a name + declared text + line, so reusing that shape there was honest.
    A macro has a PARAMETER LIST, which `ParsedVariable` has nowhere to put, and the
    parameters are written to a different table than the row itself — squeezing them
    into `declarator_text` would mean one insert helper parsing a string back apart to
    decide which table each half belongs in.

    `params` is `()` for an object-like `#define`, and ALSO for a function-like macro
    declaring no arguments (`#define F() x`). Those two are not distinguished, because
    the row shape cannot express the difference: doxygen writes parameters to
    `memberdef_param` and a zero-parameter macro produces no rows there either. Stated
    rather than papered over — `MacroDef.params` already documents `''` as "none
    recorded" instead of "takes no arguments" for exactly this reason.

    @brief One preprocessor definition: name, parameters, expansion, line.
    @version 1
    """

    name: str
    params: tuple[str, ...]
    expansion: str
    line: int


## @brief A C/C++ file's `#define`s, including ones in a branch the preprocessor drops.
## @param tree Parsed C/C++ tree.
## @param src_bytes The file's raw bytes.
## @return ParsedMacro records in source order.
## @version 1
## @req REQ-DDB-PIPE-003
def harvest_macro_definitions(tree: Any, src_bytes: bytes) -> list[ParsedMacro]:
    """SKIPS NOTHING, unlike the variable and typedef walks, and that is deliberate
    rather than an oversight. A `#define` is translation-unit scoped WHEREVER it
    textually sits: one written inside a function body or between two class members is
    still a file-scope macro, so the `function_definition` /
    `field_declaration_list` skips those walks need in order to avoid recovering locals
    and members would here DISCARD real macros for no benefit.

    It does not descend into an accepted node either, for a reason the other walks do
    not have: a function-like macro's replacement text can itself contain `#`, and
    `preproc_arg` is a single opaque token, so there is nothing to find below.

    @brief Collect a C/C++ file's preprocessor definitions.
    @return ParsedMacro records.
    @version 1
    """
    found: list[ParsedMacro] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type not in _MACRO_DEF_NODES:
            stack.extend(reversed(node.children))
            continue
        parsed = _parsed_macro(node, src_bytes)
        if parsed is not None:
            found.append(parsed)
    return found


## @brief Build a ParsedMacro from one preproc_def / preproc_function_def node.
## @param node The definition node.
## @param src_bytes The file's raw bytes.
## @return ParsedMacro, or None when the node carries no readable name.
## @version 1
## @dg_internal
def _parsed_macro(node: Any, src_bytes: bytes) -> ParsedMacro | None:
    """Fail closed on a nameless node. An error-recovered tree can produce a
    `preproc_def` whose `name` field is absent, and a row named `''` would collide with
    every other such row on the dedup key while naming nothing a caller could ask for.

    @brief Parse one `#define` into a ParsedMacro.
    @return ParsedMacro or None.
    @version 1
    """
    name_node = node.child_by_field_name(_FIELD_NAME)
    name = node_text(name_node, src_bytes) if name_node is not None else ""
    if not name:
        return None
    value_node = node.child_by_field_name(_FIELD_VALUE)
    params_node = node.child_by_field_name(_FIELD_PARAMETERS)
    params = (
        tuple(
            node_text(child, src_bytes)
            for child in params_node.children
            if child.type in _PARAM_NODES
        )
        if params_node is not None
        else ()
    )
    return ParsedMacro(
        name=name,
        params=params,
        ## `.strip()` because `preproc_arg` includes the space after the parameter list
        ## and the newline that ends the directive. doxygen's `initializer` carries
        ## neither, and two rows for one macro differing by whitespace would read as two
        ## different expansions.
        expansion=node_text(value_node, src_bytes).strip() if value_node is not None else "",
        line=node.start_point[0] + 1,
    )


## Payload keys for the two recovered symbol kinds. The payload is a MAPPING rather
## than the bare function list it used to be, so a third kind can be added without
## changing the shape again — and `stage_version` is bumped alongside, which is what
## makes an index cache written by the previous shape miss instead of being read as a
## list of functions.
_PAYLOAD_FUNCTIONS = "functions"
_PAYLOAD_VARIABLES = "variables"

## gh#395's kind. A THIRD key rather than folding typedefs into `variables`, because the two
## are written with different `memberdef.kind` values and a shared list would have to carry
## the kind per row — which is the shape that lets one loop write the wrong one.
_PAYLOAD_TYPEDEFS = "typedefs"

## gh#403's kind. A FOURTH key, and it could not have joined `variables` even by carrying a
## per-row kind: a macro record has a PARAMETER LIST and a different arity from a
## `ParsedVariable` row, so one loop reading both lists would index past the end of one.
_PAYLOAD_MACROS = "macros"


## @brief Per-file harvester for C/C++ function definitions and file-scope variables.
## @version 2
class _FunctionDefinitionHarvester(Harvester):
    """Records every function definition and every file-scope variable a C/C++ file
    contains, as line spans and identifier text. Python trees return an empty payload
    — see the module docstring on why Python needs no recovery.

    ONE HARVESTER FOR BOTH KINDS, because both are read off the same parsed tree and
    gh#358's shared parse pass warms one cache row per stage. A second harvester would
    parse every file twice to answer a question the first traversal already had in
    front of it.

    @brief Function-definition and file-scope-variable per-file harvester.
    @version 2
    """

    stage = STAGE_AST_SYMBOLS
    ## 3 -> 4: Python files now recover functions instead of returning `{}` (gh#397). A
    ## cached version-3 payload for a `.py` file holds the empty answer, so an unbumped
    ## version would leave every warm build reporting the defect this change fixes.
    ## 4 -> 5: C/C++ files now carry a `typedefs` key (gh#395). A version-4 payload has no
    ## such key, so a warm cache would serve `{}` for it and the recovered types would be
    ## missing on exactly the targets already built.
    ## 5 -> 6: C/C++ files now carry a `macros` key (gh#403). Same reasoning one kind over, and
    ## the omission would be quieter here: a version-5 payload yields no macro rows at all,
    ## so the second branch of a two-branch `#define` would stay missing on every target
    ## already built — which is the exact defect this change fixes, served from cache.
    stage_version = 6
    label = "ast symbols"

    ## @brief Harvest one file's function definitions, file-scope variables, typedefs and macros.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's raw bytes.
    ## @return Mapping of JSON-serializable records by kind; Python yields functions only.
    ## @version 5
    ## @req REQ-DDB-INDEX-004
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        """Returns plain lists rather than dataclass instances because the payload is
        JSON round-tripped through the cache — a dataclass would come back as a list
        on a cache HIT and as a dataclass on a MISS, which is the kind of shape
        divergence that only shows up on the second build.

        PYTHON NOW RECOVERS FUNCTIONS TOO (gh#397), and only functions: there is no
        Python analogue of a file-scope C variable declaration worth recovering here —
        a module-level assignment is already indexed, and `harvest_variable_declarations`
        reads C declarator shapes that the Python grammar does not produce. Nor is there a
        Python analogue of a `#define`: tree-sitter-python emits no `preproc_*` node, so
        the Python branch omits the key and never runs the macro walk — which would have
        returned an empty list, but paying for a whole traversal to learn that on every
        Python file in every repository is a cost with no answer at the end of it.

        @brief Per-file function-definition, variable, typedef and macro extraction.
        @version 4
        """
        if is_python_tree(tree):
            return {
                _PAYLOAD_FUNCTIONS: [
                    [f.name, f.qualified, f.args, int(f.static), f.start, f.end]
                    for f in harvest_python_definitions(tree, src_bytes)
                ],
                _PAYLOAD_VARIABLES: [],
            }
        return {
            _PAYLOAD_FUNCTIONS: [
                [f.name, f.qualified, f.args, int(f.static), f.start, f.end]
                for f in harvest_function_definitions(tree, src_bytes)
            ],
            _PAYLOAD_VARIABLES: [
                [v.name, v.type_text, v.declarator_text, int(v.static), v.line]
                for v in harvest_variable_declarations(tree, src_bytes)
            ],
            _PAYLOAD_TYPEDEFS: [
                [t.name, t.type_text, t.declarator_text, int(t.static), t.line]
                for t in harvest_type_definitions(tree, src_bytes)
            ],
            _PAYLOAD_MACROS: [
                [m.name, list(m.params), m.expansion, m.line]
                for m in harvest_macro_definitions(tree, src_bytes)
            ],
        }


## tree-sitter-python's node for `def`, and the body field every real definition has.
_PY_FUNCTION_DEFINITION = "function_definition"

## Python's own decorated form. A decorated `def` is wrapped in `decorated_definition`,
## so a walk that only accepts a bare `function_definition` at the top level would skip
## every `@pytest.fixture` and every `@property` — which on a test suite is most of them.
_PY_DECORATED = "decorated_definition"


## @brief A Python file's function and method definitions, qualified by enclosing class.
## @param tree Parsed tree-sitter-python tree.
## @param src_bytes The file's raw bytes.
## @return ParsedFunction records.
## @version 1
## @req REQ-DDB-PIPE-003
def harvest_python_definitions(tree: Any, src_bytes: bytes) -> list[ParsedFunction]:
    """WHY THIS EXISTS AT ALL, having been refused for the life of this module. The
    refusal's stated ground was "doxygen indexes Python fully — a Doxyfile-less Python
    codebase measured 4,739 functions — so there is nothing to recover there". That premise
    is FALSE, measured on this repository's own index at build 42:
    `tests/test_mcp_server.py` declares 93 top-level functions and doxygen emitted 41.
    Fifty-two are absent from every table, not misattributed and not truncated (rows reach
    the file's last line). So the backstop for doxygen's misses was switched off on the
    grounds that doxygen does not miss.

    The second stated ground — "a `function_definition` inside a Python `class` would need
    scope handling this stage does not do" — was true of THIS module and not of the package:
    `pyast.class_ranges`/`enclosing_class` already do exactly that, for the call-edge layer.
    Reused here rather than reimplemented, so one answer to "which class is this in" serves
    both.

    DOES NOT DESCEND INTO A DEFINITION, matching the C harvester and for the same reason: a
    closure or a nested helper would otherwise be recorded as a symbol whose span sits INSIDE
    its parent's, and the span-overlap dedup would then reject whichever it saw second,
    making the result order-dependent. Locals stay out; methods come in, qualified.

    @brief Collect a Python file's `def`s, including decorated ones and methods.
    @return ParsedFunction records.
    @version 1
    """
    ranges = class_ranges(tree, src_bytes)
    found: list[ParsedFunction] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        ## A decorated definition is a WRAPPER: descend into it so the `def` inside is seen,
        ## but never treat the wrapper itself as the symbol.
        if node.type not in (_PY_FUNCTION_DEFINITION, _PY_DECORATED):
            stack.extend(reversed(node.children))
            continue
        if node.type == _PY_DECORATED:
            stack.extend(reversed(node.children))
            continue
        parsed = _parsed_python_function(node, src_bytes, ranges)
        if parsed is not None:
            found.append(parsed)
    return found


## @brief Build a ParsedFunction from one Python `def` node.
## @param node A `function_definition` node.
## @param src_bytes The file's raw bytes.
## @param ranges Class ranges from `pyast.class_ranges`, for qualification.
## @return ParsedFunction, or None when the node carries no usable name or body.
## @version 1
## @dg_internal
def _parsed_python_function(
    node: Any, src_bytes: bytes, ranges: list[tuple[int, int, str]]
) -> ParsedFunction | None:
    """REQUIRES A BODY, like the C path, for the reason gh#11 recorded there: a node
    shaped like a definition but carrying no body is a declaration, and recovering it
    produces a row for something doxygen has already described differently.

    `static` is FALSE for every Python function, not guessed from decorators. A
    `@staticmethod` is not C's `static` — that keyword means internal linkage, and
    reporting a staticmethod as `static=True` would make `symbol_liveness` treat a public
    API method as file-private.

    @brief Parse one Python def into a ParsedFunction.
    @return ParsedFunction or None.
    @version 1
    """
    name_node = node.child_by_field_name("name")
    if name_node is None or node.child_by_field_name("body") is None:
        return None
    name = node_text(name_node, src_bytes)
    if not name:
        return None
    owner = enclosing_class(ranges, node.start_byte)
    params = node.child_by_field_name("parameters")
    return ParsedFunction(
        name=name,
        qualified=f"{owner}.{name}" if owner else name,
        args=node_text(params, src_bytes) if params is not None else "()",
        static=False,
        start=node.start_point[0] + 1,
        end=node.end_point[0] + 1,
    )


## @brief The recovered-symbol stage's harvester.
## @return A Harvester whose cache key this stage will look for.
## @version 1
## @req REQ-DDB-PIPE-003
def function_definition_harvester() -> Harvester:
    """Public factory so gh#358's shared parse pass can warm this stage's cache rows
    from the same construction site the stage itself uses. This stage still EMITS
    first — every later layer resolves endpoints to the memberdef rowids it writes —
    and sharing a parse does not share an emit.

    @brief Build this stage's harvester.
    @version 1
    """
    return _FunctionDefinitionHarvester()


## @brief Whether a table already has a named column.
## @param conn Open connection.
## @param table Table to inspect.
## @param column Column to look for.
## @return True when `PRAGMA table_info` lists the column.
## @version 1
## @dg_internal
def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """@brief Report whether a column exists on a table.

    @return True when present.
    @version 1
    """
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


## @brief Whether a table exists in this database.
## @param conn Open connection.
## @param table Table name to look for.
## @return True when `sqlite_master` lists the table.
## @version 1
## @dg_internal
def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Local rather than imported from `query._common`, which is stdlib-only BY
    DESIGN and must not acquire a pipeline importer as a reverse dependency.

    @brief Report whether a table exists.
    @return True when present.
    @version 1
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


## @brief Add the provenance column to doxygen's memberdef table, idempotently.
## @param conn Open connection to the database being built.
## @return True when the column was added, False when it was already present.
## @version 3
## @req REQ-DDB-INDEX-004
def ensure_symbol_provenance(conn: sqlite3.Connection) -> bool:
    """HOW A COLUMN GETS ONTO A TABLE WE DO NOT CREATE. `memberdef` is created by
    doxygen's own sqlite3 backend; the pipeline copies that file to `clew.db` and
    augments the copy (`doxygen.copy_database`), and it already UPDATEs, DELETEs and
    re-NAMEs rows in it — `doxygen._repair_one_attribute_row` does all three. So the
    copy is ours to alter, and `ALTER TABLE ... ADD COLUMN` is the right instrument.

    The `NOT NULL DEFAULT 'doxygen'` is the load-bearing part. It labels every row
    doxygen already wrote, retroactively and correctly, with no UPDATE sweep and no
    window in which a row exists unlabelled — which also means an index built by an
    older clew is not wrong about provenance, merely silent about it. SQLite
    rewrites the stored CREATE TABLE text, so the generated CHECK is visible in
    `sqlite_master` and the schema-reconcile test accounts for it like any other.

    Idempotent, because the R4/viewer surfaces and the tests may open a database
    that has already been through a build.

    @brief Ensure `memberdef` carries its provenance column.
    @return True when the column was newly added.
    @version 3
    """
    if _has_column(conn, "memberdef", SYMBOL_SOURCE_COLUMN):
        return False
    conn.execute(
        f"ALTER TABLE memberdef ADD COLUMN {SYMBOL_SOURCE_COLUMN} TEXT NOT NULL "
        f"DEFAULT '{SYMBOL_SOURCE_DOXYGEN}' {check('memberdef', SYMBOL_SOURCE_COLUMN)}"
    )
    return True


## @brief Every already-recorded body span, per file rowid.
## @param conn Open connection to the database being built.
## @return path rowid → list of (bodystart, bodyend) already recorded there.
## @version 2
## @dg_internal
def _covered_body_spans(conn: sqlite3.Connection) -> dict[int, list[tuple[int, int]]]:
    """DELIBERATELY UNFILTERED BY PROVENANCE, and the first cut had it the other way
    round. Restricting to `dg_source='doxygen'` was justified as "so a re-run reaches
    the same verdict", which inverted what the verdict should be: recovering nothing
    on a second pass is CORRECT — the rows are already there — and comparing against
    doxygen's spans alone made the stage insert a full duplicate set every time it
    ran. A smoke run caught it on the second call, with a UNIQUE violation on the
    synthetic refid; without that unique index it would have silently doubled the
    index. Reading every span makes the stage idempotent, and costs nothing on a
    fresh build because there are no recovered rows yet.

    Every `kind` is included, not just `'function'`: doxygen records a macro
    definition's body span too, and a function-like macro whose body a parser reads
    as a function definition must not be recovered as a second symbol.

    @brief Body line spans already attributed to each file.
    @return path rowid → (bodystart, bodyend) pairs.
    @version 2
    """
    spans: dict[int, list[tuple[int, int]]] = {}
    for file_rowid, start, end in conn.execute(
        "SELECT COALESCE(bodyfile_id, file_id), bodystart, bodyend FROM memberdef "
        "WHERE bodystart > 0"
    ):
        if file_rowid is not None:
            spans.setdefault(file_rowid, []).append((start, end))
    return spans


## @brief Every (file, name) pair the index already carries, across all kinds.
## @param conn Open connection to the database being built.
## @return Set of (path rowid, symbol name) already present.
## @version 1
## @dg_internal
def _covered_names(conn: sqlite3.Connection) -> set[tuple[int, str]]:
    """The variable dedup key, and it is `(file, name)` rather than a body span
    because a variable HAS no body span to overlap. C forbids two file-scope variables
    sharing a name within one file, so the pair is an exact identity here in a way it
    is never one for functions — where two overloads legitimately share a name and
    span dedup is the only correct rule.

    UNFILTERED BY KIND AND BY PROVENANCE, both deliberately:

      * By KIND, so a name the index already carries in that file under any kind is
        left alone. If doxygen recorded it as a macro or a function, a second row
        calling it a variable is worse than the missing row — that is exactly the
        "a variable where a caller expected a function" failure, arrived at from the
        other direction.
      * By PROVENANCE, for the reason `_covered_body_spans` records at length:
        comparing against doxygen's rows alone makes the stage insert a full duplicate
        set on every re-run. Recovering nothing the second time is CORRECT.

    Reads BOTH `file_id` and `bodyfile_id`, because a function doxygen declared in a
    header and defined in a `.c` is attributed to the header by one and the source by
    the other, and a global of the same name in the source file must lose to either.

    @brief Names already attributed to each file.
    @return Set of (file rowid, name).
    @version 1
    """
    covered: set[tuple[int, str]] = set()
    for file_rowid, name in conn.execute(
        "SELECT file_id, name FROM memberdef WHERE file_id IS NOT NULL "
        "UNION SELECT bodyfile_id, name FROM memberdef WHERE bodyfile_id IS NOT NULL"
    ):
        covered.add((file_rowid, name))
    return covered


## @brief Every (file, name, line) a definition already sits at, across all kinds.
## @param conn Open connection to the database being built.
## @return Set of (path rowid, symbol name, line) already present.
## @version 1
## @dg_internal
def _covered_macro_sites(conn: sqlite3.Connection) -> set[tuple[int, str, int]]:
    """THE MACRO DEDUP KEY, and the LINE is the whole reason gh#403 works. Neither of the
    other two keys in this module can admit the second branch of a two-branch `#define`:

      * `_covered_names`'s `(file, name)` would drop it, because doxygen already carries
        the name in that file from the branch it DID take. That is the defect.
      * `_covered_body_spans`'s overlap rule compares against `bodystart`/`bodyend`, and
        doxygen writes `bodyend = -1` on a macro row — a half-open extent that means
        something different from a function's body.

    Two `#define`s of one name cannot begin on one line, so `(file, name, line)` is an
    exact identity, and doxygen and tree-sitter agree on which line that is (verified on
    the real header: both say 15).

    ACROSS EVERY KIND, like `_covered_names` and for the same reason — a row already at
    that exact position under another kind is the same declaration, not a second one.
    That is safe here in a way a cross-kind NAME rule would not be: `MBEDTLS_PRIVATE` is
    carried ~2,000 times as `kind='function'`, one row per wrapped struct field, so a
    name-only rule would skip the macro entirely and reproduce gh#373.

    Reads `file_id` alone, not `bodyfile_id`: `line` is the line in the file the row is
    ATTRIBUTED to, and pairing it with the body's file would compare a line number from
    one file against a path from another.

    @brief Positions already occupied by a definition, for macro dedup.
    @return Set of (file rowid, name, line).
    @version 1
    """
    return {
        (file_rowid, name, line)
        for file_rowid, name, line in conn.execute(
            "SELECT file_id, name, line FROM memberdef "
            "WHERE file_id IS NOT NULL AND line IS NOT NULL"
        )
    }


## @brief Insert one recovered `#define` as an ast-sourced memberdef row plus its params.
## @param conn Open connection to the database being built.
## @param file_rowid The `path` rowid the definition lives in.
## @param macro The recovered macro.
## @version 1
## @dg_internal
def _insert_recovered_macro(conn: sqlite3.Connection, file_rowid: int, macro: ParsedMacro) -> None:
    """WRITES `initializer`, WHICH IS WHERE THE ANSWER LIVES. `macro_definitions_conn`
    reads the expansion from that column and nothing else, so a row without it would be
    findable and useless — the shape gh#373 already found once, where the layer was
    indexed and unreachable.

    NO BODY SPAN, unlike doxygen's own macro rows (`bodystart=15, bodyend=-1` on the real
    one). `_covered_body_spans` reads every kind's span to decide what function recovery
    may insert, so a `#define` carrying one could block a recoverable definition; and
    `bodyfile_id` feeds `graph_stats`'s files-with-bodies count, which a file that only
    defines macros must not join. `argsstring` stays NULL for the reason
    `_insert_recovered_variable` gives — and doxygen leaves it NULL on macro rows too,
    putting the parameters in `param` instead, which is why they are written there below.

    PARAMETERS GO TO `param`/`memberdef_param` WITH ONLY `defname` SET, exactly the shape
    doxygen produces and exactly the one `_macro_params` reads. Filling `type` or
    `declname` as well would be an invention: a macro parameter has no type. The columns
    doxygen's own dedup CORRUPTS on its rows — a real `MBEDTLS_PRIVATE` param row comes
    back wearing `type='unsigned char'`, `array='[16]'` borrowed from an unrelated
    function argument — are left NULL here, so a recovered row is cleaner than the
    emitted one rather than differently wrong.

    Skips the parameter write when either table is absent, so a partial schema loses the
    parameter list rather than the definition.

    @brief Insert one recovered macro definition and its parameter names.
    @version 1
    """
    cursor = conn.execute(
        "INSERT INTO refid (refid) VALUES (?)",
        (f"dgmac_{file_rowid}_{macro.line}_{macro.name}",),
    )
    rowid = cursor.lastrowid
    conn.execute(
        # `column` is quoted for the reason `_insert_recovered` records.
        "INSERT INTO memberdef (rowid, name, initializer, kind, static, "
        f'file_id, line, "column", {SYMBOL_SOURCE_COLUMN}) '
        "VALUES (?, ?, ?, ?, 0, ?, ?, 1, ?)",
        (rowid, macro.name, macro.expansion, MACRO_KIND, file_rowid, macro.line, SYMBOL_SOURCE_AST),
    )
    if not all(_table_exists(conn, t) for t in ("param", "memberdef_param")):
        return
    for param in macro.params:
        param_cursor = conn.execute("INSERT INTO param (defname) VALUES (?)", (param,))
        conn.execute(
            "INSERT INTO memberdef_param (memberdef_id, param_id) VALUES (?, ?)",
            (rowid, param_cursor.lastrowid),
        )


## @brief The `#define`s in one file no row already sits at.
## @param payload The file's harvested macro records.
## @param file_rowid The `path` rowid the definitions live in.
## @param covered (file, name, line) triples the index already carries.
## @return ParsedMacro records whose position is new to this file.
## @version 1
## @dg_internal
def _recoverable_macros(
    payload: Any, file_rowid: int, covered: set[tuple[int, str, int]]
) -> list[ParsedMacro]:
    """Mutates `covered` as it goes, so the file's own payload cannot produce two rows for
    one position. tree-sitter will not report one `#define` twice, but the same guard on
    the variable path exists because a `.c` declaring and then defining one global does
    exactly that, and a dedup that holds only while the parser behaves is not a dedup.

    @brief Filter a file's parsed macros to the positions not already indexed.
    @return The recoverable macros.
    @version 1
    """
    found: list[ParsedMacro] = []
    for record in payload:
        macro = ParsedMacro(
            name=record[0], params=tuple(record[1]), expansion=record[2], line=record[3]
        )
        site = (file_rowid, macro.name, macro.line)
        if site in covered:
            continue
        covered.add(site)
        found.append(macro)
    return found


## @brief Insert every recoverable `#define` from an already-run harvest.
## @param conn Open connection to the database being built.
## @param harvested (file rowid, payload) pairs from `run_harvest`.
## @return Number of macro rows inserted.
## @version 1
## @dg_internal
def _recover_macros_into(conn: sqlite3.Connection, harvested: Any) -> int:
    """RUNS LAST, after the functions, variables and typedefs, and the order is load-bearing
    in one direction only. `_covered_names` — the `(file, name)` key the variable and typedef
    passes share — matches EVERY kind, so a recovered macro row inserted first would block a
    variable of the same name in the same file. The reverse cannot happen: this pass keys on
    `(file, name, line)`, and a variable and a `#define` do not begin on one line.

    Reads the SAME harvest result as the other three passes; the parse is not repeated.

    @brief Insert the recoverable macro definitions.
    @return Rows inserted.
    @version 1
    """
    if not _table_exists(conn, "memberdef"):
        return 0
    covered = _covered_macro_sites(conn)
    inserted = 0
    for file_rowid, payload in harvested:
        for macro in _recoverable_macros(payload.get(_PAYLOAD_MACROS, []), file_rowid, covered):
            _insert_recovered_macro(conn, file_rowid, macro)
            inserted += 1
    return inserted


## @brief Insert one recovered file-scope variable as an ast-sourced memberdef row.
## @param conn Open connection to the database being built.
## @param file_rowid The `path` rowid the declaration lives in.
## @param var The recovered variable.
## @version 1
## @dg_internal
def _insert_recovered_variable(
    conn: sqlite3.Connection, file_rowid: int, var: ParsedVariable, kind: str = "variable"
) -> None:
    """WRITES NO BODY SPAN AND NO `bodyfile_id`, which is the whole discipline of this
    row. A variable is not executable: `bodystart`/`bodyend` stay NULL so
    `_covered_body_spans` cannot see it and no function recovery is ever blocked by
    one, and `bodyfile_id` stays NULL so `graph_stats`'s "files with bodies" count
    does not grow by a file that only declares a global. `argsstring` stays NULL for
    the same reason: a variable has no parameter list, and an empty `()` would read
    like a nullary function.

    `kind='variable'` is doxygen's OWN vocabulary value for this — it already writes
    902 such rows on mbedtls — so this adds no column, no table and no CHECK value,
    and every layer that filters `kind='function'` excludes it for free. `type` holds
    the declared type text, which is what lets a reader tell mbedtls's mutex OBJECTS
    (`mbedtls_threading_mutex_t`) from its lock PRIMITIVE (a `void (*)(...)`).

    Allocates the rowid from `refid` for the reason `_insert_recovered` gives; the
    synthetic refid is namespaced `dgvar_` so the two recovery kinds cannot collide on
    a file and line where a variable and a function start on the same row.

    @brief Insert one recovered file-scope variable.
    @version 1
    """
    cursor = conn.execute(
        "INSERT INTO refid (refid) VALUES (?)",
        (f"dgvar_{file_rowid}_{var.line}_{var.name}",),
    )
    conn.execute(
        # `column` is quoted for the reason `_insert_recovered` records.
        # `kind` is BOUND, not interpolated, and it is a parameter rather than a literal
        # because gh#395 recovers typedefs through this same shape — a typedef has a name, a
        # line and no body, which is exactly what `ParsedVariable` models. Both values are
        # doxygen's own vocabulary, so neither needs a schema change.
        "INSERT INTO memberdef (rowid, name, definition, type, kind, static, "
        f'file_id, line, "column", {SYMBOL_SOURCE_COLUMN}) '
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (
            cursor.lastrowid,
            var.name,
            var.definition(),
            var.type_text,
            kind,
            int(var.static),
            file_rowid,
            var.line,
            SYMBOL_SOURCE_AST,
        ),
    )


## @brief The variables in one file the index does not already name.
## @param payload The file's harvested variable records.
## @param file_rowid The `path` rowid the declarations live in.
## @param covered (file, name) pairs the index already carries.
## @return ParsedVariable records whose name is new to this file.
## @version 1
## @dg_internal
def _recoverable_variables(
    payload: Any, file_rowid: int, covered: set[tuple[int, str]]
) -> list[ParsedVariable]:
    """Also dedups WITHIN the file's own payload, via the `covered` set it mutates as
    it goes. Two `declaration` nodes can name the same global — a `.c` file that
    declares `extern int x;` and then defines `int x = 0;` does exactly that — and
    without this the stage would emit two rows for one variable, which is the failure
    mode this whole dedup exists to prevent, reintroduced one scope in.

    @brief Filter a file's parsed variables to the ones not already indexed.
    @return The recoverable variables.
    @version 1
    """
    found: list[ParsedVariable] = []
    for record in payload:
        var = ParsedVariable(
            name=record[0],
            type_text=record[1],
            declarator_text=record[2],
            static=bool(record[3]),
            line=record[4],
        )
        if (file_rowid, var.name) in covered:
            continue
        covered.add((file_rowid, var.name))
        found.append(var)
    return found


## @brief The definitions in one file that doxygen did not already cover.
## @param payload The file's harvested definition records.
## @param covered Body spans doxygen attributed to this file.
## @return ParsedFunction records whose spans overlap nothing doxygen recorded.
## @version 1
## @dg_internal
def _recoverable(payload: Any, covered: list[tuple[int, int]]) -> list[ParsedFunction]:
    """@brief Drop parsed definitions that overlap a doxygen body span.

    @return The recoverable definitions.
    @version 1
    """
    parsed = [
        ParsedFunction(
            name=r[0], qualified=r[1], args=r[2], static=bool(r[3]), start=r[4], end=r[5]
        )
        for r in payload
    ]
    return [f for f in parsed if not any(f.overlaps(s, e) for s, e in covered)]


## @brief Insert one recovered definition as an ast-sourced memberdef row.
## @param conn Open connection to the database being built.
## @param file_rowid The `path` rowid the definition lives in.
## @param fn The recovered definition.
## @version 1
## @dg_internal
def _insert_recovered(conn: sqlite3.Connection, file_rowid: int, fn: ParsedFunction) -> None:
    """Allocates the rowid from `refid` exactly as doxygen does — doxygen keeps
    `memberdef.rowid == refid.rowid` and declares the foreign key, so letting
    `memberdef` auto-assign would quietly break that invariant even though SQLite
    does not enforce it by default. The synthetic refid is namespaced and carries
    the file and line, so it is unique and traceable back to what produced it.

    `file_id` and `bodyfile_id` are BOTH this file, which makes the row a
    DEFINITION row under `_definition_preferring_name_index` and
    `_common.function_candidates` — correct, because a parsed definition is
    precisely a body. `briefdescription`, `detaileddescription` and
    `inbodydescription` are left NULL and are never written: there is no
    documentation behind an unsatisfied preprocessor guard.

    @brief Insert one recovered function definition.
    @version 1
    """
    cursor = conn.execute(
        "INSERT INTO refid (refid) VALUES (?)",
        (f"dgast_{file_rowid}_{fn.start}_{fn.name}",),
    )
    conn.execute(
        # `column` is quoted: SQLite treats it as a keyword (ALTER TABLE RENAME
        # COLUMN), and an unquoted one is a syntax error on some builds.
        "INSERT INTO memberdef (rowid, name, definition, argsstring, kind, static, "
        'bodystart, bodyend, bodyfile_id, file_id, line, "column", '
        f"{SYMBOL_SOURCE_COLUMN}) VALUES (?, ?, ?, ?, 'function', ?, ?, ?, ?, ?, ?, 1, ?)",
        (
            cursor.lastrowid,
            fn.name,
            fn.qualified,
            fn.args,
            int(fn.static),
            fn.start,
            fn.end,
            file_rowid,
            file_rowid,
            fn.start,
            SYMBOL_SOURCE_AST,
        ),
    )


## @brief Recover the function definitions doxygen did not emit.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root the indexed paths are relative to.
## @param cache Optional incremental index cache; None disables caching.
## @return Number of memberdef rows inserted.
## @version 1
## @req REQ-DDB-INDEX-004
def recover_ast_symbols(
    db_path: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
) -> int:
    """MUST run before every call-edge layer and after `repair_attribute_named_functions`.

    Before the call layers, because those resolve their endpoints to memberdef
    rowids — recovering a symbol afterwards would give it a row and no edges, which
    is the defect in a subtler form. After the `__attribute__` repair, because that
    pass merges and renames doxygen's own rows, and the spans this stage compares
    against must be the repaired ones.

    Returns 0 without touching the database when tree-sitter is unavailable or
    `memberdef`/`refid` are absent, so a build with no grammars installed is
    unchanged rather than failed.

    @brief Insert ast-sourced memberdef rows for parser-visible definitions.
    @return Rows inserted.
    @version 1
    """
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        inserted = _recover_into(conn, repo_root, ts_classes, cache)
        conn.commit()
    finally:
        conn.close()
    return inserted


## @brief Run the harvest and insert every recoverable definition.
## @param conn Open connection to the database being built.
## @param repo_root Repository root the indexed paths are relative to.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param cache Optional incremental index cache.
## @return Number of memberdef rows inserted.
## @version 4
## @dg_internal
def _recover_into(
    conn: sqlite3.Connection,
    repo_root: Path,
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None,
) -> int:
    """Split from `recover_ast_symbols` so the connection's lifetime is owned in one
    place and this function can early-return on a schema it cannot use.

    FUNCTIONS ARE INSERTED BEFORE VARIABLES, and the order is load-bearing: the
    variable dedup key is `(file, name)` read from `memberdef`, so `_covered_names` has
    to be computed AFTER the recovered functions are in the table. Computed before, a
    file whose global shares a name with a function this same stage just recovered
    would get a second row under a second kind — which is precisely the confusion
    `kind` exists to prevent.

    MACROS LAST, for the mirror image of that reason — see `_recover_macros_into`.

    @brief Harvest, dedup and insert every recovered kind, reporting the row count.
    @return Rows inserted.
    @version 4
    """
    if not all(_table_exists(conn, t) for t in ("memberdef", "refid", "path")):
        return 0
    ensure_symbol_provenance(conn)
    covered = _covered_body_spans(conn)
    harvested = run_harvest(conn, repo_root, function_definition_harvester(), ts_classes, cache)
    functions = 0
    for file_rowid, payload in harvested:
        for fn in _recoverable(payload.get(_PAYLOAD_FUNCTIONS, []), covered.get(file_rowid, [])):
            _insert_recovered(conn, file_rowid, fn)
            functions += 1
    variables = _recover_variables_into(conn, harvested)
    macros = _recover_macros_into(conn, harvested)
    if functions:
        logger.info(
            "ast symbols: recovered %d function definition(s) doxygen did not emit "
            "(no brief, no @req — declare PREDEFINED to document them)",
            functions,
        )
    if variables:
        logger.info(
            "ast symbols: recovered %d file-scope variable(s) doxygen did not emit "
            "(kind='variable' — no body, no callers, no callees)",
            variables,
        )
    if macros:
        logger.info(
            "ast symbols: recovered %d macro definition(s) doxygen did not emit "
            "(kind='macro definition' — the #else branch of a conditional #define is "
            "the case doxygen's preprocessor cannot reach)",
            macros,
        )
    return functions + variables + macros


## @brief Insert every recoverable file-scope variable and typedef from an already-run harvest.
## @param conn Open connection to the database being built.
## @param harvested (file rowid, payload) pairs from `run_harvest`.
## @return Number of variable and typedef rows inserted.
## @version 2
## @dg_internal
def _recover_variables_into(conn: sqlite3.Connection, harvested: Any) -> int:
    """Split out of `_recover_into` to keep that function inside the house complexity
    limit once it grew a second kind, and to give the ordering comment there one place
    to point at. Reads the SAME harvest result — the parse is not repeated.

    @brief Insert the recoverable variables.
    @return Rows inserted.
    @version 1
    """
    covered = _covered_names(conn)
    inserted = 0
    ## ONE `covered` SET ACROSS BOTH KINDS, deliberately. `_covered_names` already dedups by
    ## `(file, name)` across EVERY kind for the reason it records — a name the index carries
    ## in that file is left alone rather than duplicated under a second kind — and a typedef
    ## sharing its name with a variable in one file is precisely that case.
    for kind, key in (("variable", _PAYLOAD_VARIABLES), ("typedef", _PAYLOAD_TYPEDEFS)):
        for file_rowid, payload in harvested:
            for var in _recoverable_variables(payload.get(key, []), file_rowid, covered):
                _insert_recovered_variable(conn, file_rowid, var, kind)
                inserted += 1
    return inserted
