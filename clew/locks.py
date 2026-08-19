# SPDX-License-Identifier: MIT
"""R1 lock layer, L1: where locks are declared and where they are acquired.

clew could already say two threads touch the same key; it had no way to say
whether that access is GUARDED. This is the facts half of closing that: two
tables of things observed in the AST, with no inference layered on top.

  `locks`              — a mutex's identity: name + SCOPE + kind.
  `lock_acquisitions`  — a site where some function takes one, with its extent.

Both real codebases are covered, and they use genuinely different idioms:
  C++ codebase     — RAII guards. `std::lock_guard<std::mutex> g(mutex_);` holds
                 until the end of the enclosing block. A DECLARATION, not a
                 call, so it is invisible to the call-site harvester the rest
                 of the pipeline is built on and needs its own node handling.
  C/POSIX repo — explicit `pthread_mutex_lock(&m)` / `..._unlock(&m)` pairs.
                 These ARE call expressions, so the extent comes from finding
                 the matching unlock rather than from a scope.

IDENTITY IS SCOPE-QUALIFIED AND FAILS CLOSED. A lock is keyed by (name, scope,
kind), where scope is `class:Foo`, `global`, or `file:<repo-rel path>`. When the
scope cannot be determined the row is kept with `identity_confidence='low'`
rather than merged into a same-named lock elsewhere. In real C++ code the member name
`mutex_` recurs across many classes, so name-only keying would report unrelated
classes as sharing a mutex — the same collision that made `thread_of` answer
wrongly (#42) and made the first cut of the event importer fabricate 5294 edges
(#47). For race analysis a false MERGE is the worst available error: it invents
a shared lock, which is indistinguishable from real synchronization.

NO HARDCODING: the primitives below are language/OS-level (std::*, pthread_*,
POSIX semaphores), not any repo's convention. A project's own wrapper type
(`ScopedLock`, `MutexGuard`) is DECLARED in the repo's `.clew.yaml` under
`locks:` — reachable from both entry points since #51.

Deliberately NOT here: lock ordering / deadlock cycles. Measured across both
codebases' indexed scopes there are ZERO simultaneous two-lock holdings
WITHIN one function, so a cycle detector would have nothing to validate against.
Cross-function ordering is the case that matters, and `critical_sections` (L2)
is what makes it derivable — join `critical_section_calls.callee_rowid` against
`lock_acquisitions.holder_rowid` and a hold that spans a call becomes visible.
Ordering itself is still deliberately absent: it is re-measured from that data,
not guessed at now.

EXTENTS COME FROM L2. `end_line` used to be found by popping a DFS stack and
taking whichever matching unlock it reached first, which made the extent depend
on traversal order; and it accepted a release sealed inside an early-return
branch as the end of the hold, understating a sixteen-line critical section as a
two-line one. `critical_sections.resolve_section` now produces the extent and
the membership from ONE analysis, so the two cannot disagree.

@brief Lock declarations and acquisition sites (R1 lock layer, L1).
@version 2
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .critical_sections import (
    EXTENT_UNRESOLVED,
    Section,
    ensure_section_table,
    insert_section_calls,
    resolve_section,
)
from .declaration import SECTION_LOCKS
from .harvest import Harvester, enclosing, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .pyast import node_text
from .treescan import manifest_key
from .vocabulary import (
    ACQ_FORM,
    ACQ_MODE,
    ACQ_ROLE,
    LOCK_KIND,
    STAGE_LOCKS,
    bool_check,
    check,
    declaration_origin,
)

## Scope sentinel for a lock whose owner could not be determined. Kept distinct
## from 'global' so a consumer can tell "we know it is a global" from "we do
## not know what this is" — the fail-closed half of scope-qualified identity.
SCOPE_UNKNOWN = "unknown"


## @brief One lock primitive convention: how it is written and what it means.
## @version 1
class LockPattern:
    """A lock-acquisition convention: the token that names it, whether it is a
    RAII declaration or a call, the mutex operand's argument index, the kind of
    primitive, and whether it takes shared or exclusive ownership.

    @brief Lock-acquisition convention.
    @version 1
    """

    __slots__ = ("form", "kind", "mode", "name", "operand_index", "releases", "role")

    ## @brief Store one lock convention.
    ## @param name Token naming the acquisition.
    ## @param form "raii" (declaration) or "call".
    ## @param operand_index Argument index holding the mutex operand.
    ## @param kind Primitive kind.
    ## @param mode Shared or exclusive ownership.
    ## @param role Acquisition role.
    ## @param releases For a `call` form, the token that ENDS the hold.
    ## @version 2
    ## @dg_internal
    def __init__(
        self,
        name: str,
        form: str,
        operand_index: int = 0,
        kind: str = "mutex",
        mode: str = "exclusive",
        role: str = "scoped",
        releases: str = "",
    ) -> None:
        self.name = name
        self.form = form
        self.operand_index = operand_index
        self.kind = kind
        self.mode = mode
        self.role = role
        ## The release counterpart, for a DECLARED call-form wrapper. Built-in
        ## primitives get theirs from `_RELEASERS`; a repo's own wrapper had no
        ## route at all, so its extent could never close and every acquisition
        ## reported a NULL end_line. Measured on a real C library: 5 acquisition
        ## sites detected, 0 with a resolved extent, purely for want of this
        ## field. RAII forms leave it empty — their hold ends with the block.
        self.releases = releases


# Language/OS primitives — repo-independent, so both reference idioms work with
# zero configuration. Repo-specific WRAPPERS are declared, never guessed.
DEFAULT_LOCK_PATTERNS: list[LockPattern] = [
    # C++ RAII guards: a DECLARATION whose extent is the enclosing block.
    LockPattern("lock_guard", form="raii", kind="mutex", mode="exclusive"),
    LockPattern("unique_lock", form="raii", kind="mutex", mode="exclusive"),
    LockPattern("scoped_lock", form="raii", kind="mutex", mode="exclusive"),
    LockPattern("shared_lock", form="raii", kind="shared_mutex", mode="shared"),
    # C/POSIX explicit pairs: a CALL whose extent runs to the matching unlock.
    LockPattern("pthread_mutex_lock", form="call", kind="mutex", role="acquire"),
    LockPattern("pthread_mutex_trylock", form="call", kind="mutex", role="try_acquire"),
    LockPattern("pthread_rwlock_wrlock", form="call", kind="shared_mutex", role="acquire"),
    LockPattern(
        "pthread_rwlock_rdlock", form="call", kind="shared_mutex", mode="shared", role="acquire"
    ),
    LockPattern("sem_wait", form="call", kind="semaphore", role="acquire"),
    # Rust std::sync::{Mutex,RwLock}: the guard returned by .lock()/.read()/
    # .write() (bare, or through .unwrap()/.expect()/`?` — parking_lot's
    # Mutex::lock() returns the guard directly with no Result at all, which is
    # why the bare-call shape is matched too) is dropped at end of scope
    # exactly like a C++ RAII guard. form="raii" is therefore correct even
    # though detection is a CALL, not a declared guard type — see
    # _visit_rust_lock_binding, which is what actually finds these (Rust has
    # no generic "declaration" node for _visit_declaration's type-name match
    # to key on).
    LockPattern("lock", form="raii", kind="mutex", mode="exclusive"),
    LockPattern("try_lock", form="raii", kind="mutex", mode="exclusive"),
    LockPattern("read", form="raii", kind="shared_mutex", mode="shared"),
    LockPattern("try_read", form="raii", kind="shared_mutex", mode="shared"),
    LockPattern("write", form="raii", kind="shared_mutex", mode="exclusive"),
    LockPattern("try_write", form="raii", kind="shared_mutex", mode="exclusive"),
]

# The release counterpart of each `call`-form primitive, so an extent can be
# closed. RAII forms need no entry: their extent is the enclosing scope.
_RELEASERS = {
    "pthread_mutex_lock": "pthread_mutex_unlock",
    "pthread_mutex_trylock": "pthread_mutex_unlock",
    "pthread_rwlock_wrlock": "pthread_rwlock_unlock",
    "pthread_rwlock_rdlock": "pthread_rwlock_unlock",
    "sem_wait": "sem_post",
}

# A mutex member declaration, used to attribute a lock to its owning class:
#   `mutable std::mutex mutex_;`  /  `std::recursive_mutex m;`

# Ownership TAGS, not mutexes. Filtering these by name is deliberate and narrow:
# an earlier cut dropped anything containing "_lock", which silently discarded
# every real mutex called `g_lock` / `data_lock` — the common C naming.
_LOCK_TAGS = frozenset(
    {
        "std::adopt_lock",
        "adopt_lock",
        "std::defer_lock",
        "defer_lock",
        "std::try_to_lock",
        "try_to_lock",
    }
)

# `g(mutex_)` at declaration position parses as a function_declarator (the most
# vexing parse), so the operand arrives in a parameter_list rather than an
# `arguments` field; brace init gives an initializer_list.
_OPERAND_LISTS = ("argument_list", "parameter_list", "initializer_list")


## @brief Merge a repo's declared lock wrappers over the built-in primitives.
## @param source Declared `locks:` section (mapping), a YAML path, or None.
## @return Merged pattern list; declared entries override a default by name.
## @version 2
## @req REQ-DDB-SCHEMA-011
def load_lock_patterns(source: Path | dict | None) -> list[LockPattern]:
    """Expected shape, mirroring the thread/accessor manifests::

        locks:
          - name: "ScopedLock"       # a project's own RAII wrapper
            form: "raii"
            kind: "mutex"
          - name: "bsp_lock_take"    # a project's own call-form primitive
            form: "call"
            operand_index: 0

    An invalid `form`/`kind`/`role`/`mode` RAISES `DeclarationError` naming the
    file, the token and the allowed set. Two of these were unguarded before:
    `role` rode straight into the INSERT and surfaced as a bare `IntegrityError`
    mid-build, while `form`/`mode` silently coerced anything that was not the
    exact non-default spelling into the default — so `form: "cal"` became an
    RAII guard and `mode: "shard"` became an exclusive hold. Both are specific,
    real synchronization claims invented from a typo.

    `kind` in particular CANNOT fall back: it is part of lock identity
    (`UNIQUE(name, scope, kind)`), so two differently-typo'd kinds normalizing
    to one token merge unrelated acquisitions into a single lock row — the
    fabricated-shared-lock error this module's identity rule exists to prevent.

    @brief Merge declared lock conventions over the defaults.
    @return Merged LockPattern list.
    @version 2
    """
    merged: dict[str, LockPattern] = {p.name: p for p in DEFAULT_LOCK_PATTERNS}
    data = _pattern_document(source)
    origin = declaration_origin(source, SECTION_LOCKS)
    for entry in data.get("locks", []) or []:
        name = entry.get("name")
        if not name:
            continue
        merged[name] = _declared_lock_pattern(entry, name, f"{origin}: lock pattern {name!r}")
    return list(merged.values())


## @brief Build one LockPattern from a declared entry, validating every enum.
## @param entry The declared `locks:` list entry.
## @param name The pattern's declared name.
## @param owner Origin label for a fail-closed error message.
## @return A LockPattern whose enum fields are all vocabulary members.
## @version 2
## @dg_internal
def _declared_lock_pattern(entry: dict, name: str, owner: str) -> LockPattern:
    """Split out of `load_lock_patterns` so all four enum fields go through one
    validation shape rather than three different ad-hoc ones.

    `form` is validated against the `lock_acquisitions.form` vocabulary, which
    also carries `'declared'`. That third value is reserved for a future
    declared-acquisition path and matches neither detector here, so a pattern
    declaring it finds nothing — fail-closed, but worth knowing: a PATTERN's
    form is only ever `'call'` or `'raii'`.

    @brief Validate and construct one declared lock pattern.
    @version 2
    """
    return LockPattern(
        name=name,
        form=ACQ_FORM.validated(str(entry.get("form", "raii")), owner=owner, field="form"),
        operand_index=int(entry.get("operand_index", 0)),
        kind=LOCK_KIND.validated(str(entry.get("kind", "mutex")), owner=owner, field="kind"),
        mode=ACQ_MODE.validated(str(entry.get("mode", "exclusive")), owner=owner, field="mode"),
        role=ACQ_ROLE.validated(str(entry.get("role", "scoped")), owner=owner, field="role"),
        ## Free-form on purpose: it names a function in the TARGET repo, so no
        ## vocabulary can enumerate the valid values. Unvalidated here means a
        ## typo yields no matching release token and the extent stays NULL —
        ## which is the same honest answer as declaring nothing, not a fabricated
        ## critical section.
        releases=str(entry.get("releases", "")).strip(),
    )


## @brief Normalize the manifest source into a mapping.
## @param source Mapping, path, or None.
## @return The parsed document, or {} when there is nothing to read.
## @version 1
## @dg_internal
def _pattern_document(source: Path | dict | None) -> dict:
    """@brief Accept a declared section or a standalone YAML path."""
    if source is None:
        return {}
    if isinstance(source, dict):
        return source
    import yaml

    return yaml.safe_load(Path(source).read_text(encoding="utf-8")) or {}


## @brief Create the L1 lock tables if they do not exist.
## @param conn Open connection to the database being built.
## @return None.
## @version 3
## @dg_internal
def _ensure_lock_tables(conn: sqlite3.Connection) -> None:
    """Always created, even when tree_sitter is absent or the repo has no
    locks, so R2/R4 never branch on table existence — the requirements.py
    precedent the thread layer also follows.

    Every column in a UNIQUE key is NOT NULL: a NULL there silently defeats
    dedup in SQLite, and the downstream symptom would be a duplicated lock
    identity, i.e. a fabricated distinction between one mutex and itself.

    Every enumerated CHECK is generated from `vocabulary.COLUMNS`. The three
    that used to be generated here did it with `{tuple!r}`, which emits
    `IN ('x',)` for a one-value set — SQLite rejects the trailing comma. They
    only ever worked because both tuples happened to have three or more values.

    L2's `critical_section_calls` is created here too, so ONE call gives a
    caller the whole lock layer and the always-created contract extends to the
    membership table. The schema-reconcile test builds its fixture from the
    pipeline's own table creators, so a separately-created table would be
    registered in the vocabulary and absent from the shipped schema.

    @brief Create locks + lock_acquisitions + critical_section_calls.
    @version 3
    """
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS locks (
            id                  INTEGER PRIMARY KEY,
            name                TEXT NOT NULL,
            scope               TEXT NOT NULL,
            kind                TEXT NOT NULL {check("locks", "kind")},
            decl_path_rowid     INTEGER REFERENCES path(rowid),
            decl_line           INTEGER,
            identity_confidence TEXT NOT NULL {check("locks", "identity_confidence")},
            source              TEXT NOT NULL {check("locks", "source")},
            UNIQUE(name, scope, kind)
        );
        CREATE TABLE IF NOT EXISTS lock_acquisitions (
            id           INTEGER PRIMARY KEY,
            lock_id      INTEGER REFERENCES locks(id),
            holder_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            path_rowid   INTEGER NOT NULL REFERENCES path(rowid),
            form         TEXT NOT NULL {check("lock_acquisitions", "form")},
            role         TEXT NOT NULL {check("lock_acquisitions", "role")},
            mode         TEXT NOT NULL {check("lock_acquisitions", "mode")},
            start_line   INTEGER NOT NULL,
            end_line     INTEGER,
            pattern_name TEXT NOT NULL,
            declared     INTEGER NOT NULL {bool_check("declared")},
            confidence   TEXT NOT NULL {check("lock_acquisitions", "confidence")},
            UNIQUE(holder_rowid, start_line, pattern_name)
        );
        CREATE INDEX IF NOT EXISTS idx_lock_acq_lock ON lock_acquisitions(lock_id);
        CREATE INDEX IF NOT EXISTS idx_lock_acq_holder ON lock_acquisitions(holder_rowid);
        """
    )
    ensure_section_table(conn)


## @brief Text of a node, decoded, tolerating an absent node.
## @param node Tree-sitter node (may be None).
## @param src Source bytes.
## @return Decoded text, or "" when the node is absent.
## @version 2
## @dg_internal
def _text(node: Any, src: bytes) -> str:
    """A None guard over the shared decoder rather than a second copy of it —
    several call sites here pass a `child_by_field_name` result straight in, and
    an absent optional field is normal, not an error.

    @brief Decode one node's source span, or "" when it is absent.
    @version 2
    """
    return "" if node is None else node_text(node, src)


## @brief The class/struct a node sits inside, for scope-qualified identity.
## @param node Node to locate.
## @param src Source bytes.
## @return "class:Foo", or SCOPE_UNKNOWN when there is no enclosing class.
## @version 4
## @dg_internal
def _class_scope(node: Any, src: bytes) -> str:
    """A mutex named `mutex_` is meaningless on its own — a codebase has many. The
    owning class is what makes the identity real, so it is resolved from the
    AST rather than assumed, and absence is reported as unknown rather than
    silently collapsing into a global.

    Rust has no C++-style out-of-line member definition to fall back to
    (`impl Foo { fn bar(&self) {...} }` always nests the method lexically
    inside its `impl` block, unlike `void Foo::bar() {...}` in a .cpp file) —
    so `impl_item`'s own `type` field is the whole answer for Rust, and
    `_out_of_line_scope`'s qualified-name recovery correctly finds nothing
    to do for it (Rust has no `function_definition` node either).

    @brief Resolve the enclosing class scope of a node.
    @return Scope string.
    @version 4
    """
    holder = enclosing(node, ("class_specifier", "struct_specifier", "impl_item"))
    if holder is not None:
        name_field = "type" if holder.type == "impl_item" else "name"
        name = _text(holder.child_by_field_name(name_field), src)
        return f"class:{name}" if name else SCOPE_UNKNOWN
    return _out_of_line_scope(node, src)


## @brief Class scope taken from an out-of-line member definition's name.
## @param node Node inside the function body.
## @param src Source bytes.
## @return "class:Foo", or SCOPE_UNKNOWN.
## @version 4
## @dg_internal
def _out_of_line_scope(node: Any, src: bytes) -> str:
    """Most acquisitions live in a .cpp member definition — `void
    LinkOwner::tx_loop() { ... }` — which has NO enclosing class_specifier,
    so the class has to come from the qualified function name instead.
    Measured on real C++ source: reading only the enclosing class node left most
    acquisitions scope-unknown, which would have made almost every lock fail
    closed and the layer look far emptier than the code is.

    A POINTER OR REFERENCE RETURN TYPE PUTS ITS SIGIL INSIDE THE DECLARATOR. For
    `Slot* SecondaryModelLoader::acquire()` tree-sitter's declarator text is
    `* SecondaryModelLoader::acquire`, so the naive qualifier is `* SecondaryModelLoader` and
    the scope came out as `class:* SecondaryModelLoader`. Because scope is part of lock
    IDENTITY, that split one mutex into two rows — the same lock counted twice, differing
    only by a sigil that belongs to the return type and says nothing about the owner.

    Measured on the public entropic index at build version 14: 4 of 56 lock rows carried a
    starred scope, and every one of them was a duplicate of a `class:X` twin with the same
    name AND the same kind — `mutex_`/PromptCache, `slots_mutex_`/SecondaryModelLoader,
    `swap_mutex_`/ModelOrchestrator, `identities_mutex_`/IdentityManager. A 7% inflation of
    the lock count, in the direction that matters least forgivingly: the layer's whole claim
    is that identity is scope-qualified so unrelated `mutex_` members cannot merge, and this
    was the same mechanism splitting a lock from itself.

    Found by the entropic acceptance grid rather than by a test, which is what the grid is
    for — no unit test pins a count that only a real C++ codebase produces.

    @brief Recover class scope from a qualified function definition.
    @return Scope string.
    @version 4
    """
    fn = enclosing(node, ("function_definition",))
    if fn is None:
        return SCOPE_UNKNOWN
    declarator = _text(fn.child_by_field_name("declarator"), src).split("(")[0]
    qualifier = declarator.rsplit("::", 1)[0] if "::" in declarator else ""
    owner = qualifier.split("::")[-1].lstrip("*& \t") if qualifier else ""
    return f"class:{owner}" if owner else SCOPE_UNKNOWN


## @brief Operand identifiers passed to a guard/lock construct.
## @param args Argument-list node.
## @param src Source bytes.
## @return Identifier-ish operand names, tag arguments dropped.
## @version 1
## @dg_internal
def _operand_names(args: Any, src: bytes) -> list[str]:
    """Keep only plain operands. `std::adopt_lock` / `std::defer_lock` are
    TAGS, not mutexes, and counting them would invent a lock that does not
    exist — the fail-closed rule again.

    @brief Extract mutex operand names from an argument list.
    @return Operand names.
    @version 1
    """
    if args is None:
        return []
    names = []
    for child in args.named_children:
        raw = _text(child, src).strip().lstrip("&*").split("(")[0].strip()
        if raw and raw not in _LOCK_TAGS:
            names.append(raw)
    return names


## @brief The node holding a guard declaration's constructor operands.
## @param declarator The declaration's declarator node (may be None).
## @return The operand list node, or None.
## @version 1
## @dg_internal
def _operand_list(declarator: Any) -> Any:
    """@brief Find the argument/parameter/initializer list under a declarator."""
    if declarator is None:
        return None
    return next((c for c in declarator.children if c.type in _OPERAND_LISTS), None)


## @brief Every lock primitive name in play, so L2 can exclude them as members.
## @param patterns Active pattern lookup by name (defaults + declared).
## @return Acquire and release primitive names.
## @version 3
## @dg_internal
def _primitive_names(patterns: dict) -> frozenset[str]:
    """Derived from the ACTIVE patterns rather than written out, so a repo that
    DECLARES its own wrapper gets it excluded too — a hardcoded list would work
    for pthread and silently fail for the exact conventions the declaration
    mechanism exists to support.

    Declared `releases:` tokens are included for the same reason: a repo's own
    unlock wrapper is synchronization, and omitting it would count every release
    call as ordinary work inside its own critical section.

    @brief The acquire/release names that are synchronization, not work.
    @version 4
    """
    declared = {p.releases for p in patterns.values() if getattr(p, "releases", "")}
    return frozenset(patterns) | frozenset(_RELEASERS.values()) | frozenset(declared)


## @brief Resolve one acquisition's extent + membership, failing closed.
## @param node The acquiring declaration (RAII) or call node.
## @param src Source bytes.
## @param pattern The matched lock pattern.
## @param operand Mutex operand name.
## @param primitives Lock primitive names L2 must not record as members.
## @return The resolved Section.
## @version 4
## @dg_internal
def _section_for(
    node: Any,
    src: bytes,
    pattern: LockPattern,
    operand: str,
    primitives: frozenset[str] = frozenset(),
) -> Section:
    """An RAII guard needs no release token — its hold ends with the enclosing
    block by language rule — so `None` is passed and L2 reads the block extent.

    A `call`-form pattern with NO known release counterpart is refused outright
    rather than falling through to the block extent. This is the fail-open the
    unified walk would otherwise introduce: treating a lock whose release is
    unknown as block-scoped would report a whole function as one critical section
    on no evidence at all.

    THE DECLARED `releases:` FIELD is that follow-up, now implemented. Before it,
    a repo could declare its acquire wrapper but had no way to name the matching
    release, so `_RELEASERS` — a module-level dict of built-in primitives only —
    could never cover it and EVERY acquisition on a wrapper reported a NULL
    extent. Measured on a real C library using an `mbedtls_mutex_lock`-style
    wrapper: 5 acquisition sites detected, 0 with a resolved extent, purely for
    want of somewhere to write the counterpart down.

    A declared `releases:` wins over the built-in map, so a repo can also correct
    a primitive whose pairing it uses differently.

    @brief Choose the release convention for one acquisition, or refuse.
    @version 3
    """
    if pattern.form == "raii":
        return resolve_section(node, src, None, operand, primitives)
    releaser = pattern.releases or _RELEASERS.get(pattern.name)
    if not releaser:
        return Section(None, [], EXTENT_UNRESOLVED)
    return resolve_section(node, src, releaser, operand, primitives)


## @brief Append one acquisition site record, extent and membership included.
## @param node The acquiring node.
## @param src Source bytes.
## @param pattern The matched lock pattern.
## @param operand Mutex operand name.
## @param role Acquisition role for this form.
## @param sites Accumulator.
## @param primitives Lock primitive names L2 must not record as members.
## @return None.
## @version 2
## @dg_internal
def _append_site(
    node: Any,
    src: bytes,
    pattern: LockPattern,
    operand: str,
    role: str,
    sites: list,
    primitives: frozenset[str],
) -> None:
    """Shared by both idioms so the record SHAPE is written once: the RAII and
    call visitors previously built the same nine-field list twice, which is
    exactly how a tenth field gets added to one of them only.

    @brief Build one rowid-free acquisition record.
    @version 2
    """
    section = _section_for(node, src, pattern, operand, primitives)
    sites.append(
        [
            pattern.name,
            operand,
            _class_scope(node, src),
            node.start_point[0] + 1,
            section.end_line,
            pattern.form,
            pattern.kind,
            pattern.mode,
            role,
            section.confidence,
            section.calls,
        ]
    )


## @brief The declared type's own name, with template arguments removed.
## @param type_text Raw text of a declaration's `type` field.
## @return The base type spelling, qualifiers kept, or "" when unreadable.
## @version 1
## @dg_internal
def _base_type_name(type_text: str) -> str:
    """`std::lock_guard<std::mutex>` names the type `std::lock_guard`; the rest
    is the MUTEX, not the guard. Template arguments are stripped by balanced
    depth rather than by truncating at the first `<`, so a guard reached through
    a dependent scope (`Outer<T>::lock_guard`) keeps its own name instead of
    collapsing to `Outer`.

    Storage/cv keywords (`const std::lock_guard`) are shed by keeping the last
    whitespace-separated token, and any pointer/reference sigil with it — a RAII
    guard is never spelled through one, so a leftover sigil could only ever
    prevent a real match.

    @brief Strip template arguments and qualifiers from a declared type.
    @return Base type spelling.
    @version 1
    """
    kept: list[str] = []
    depth = 0
    for char in type_text:
        depth += char == "<"
        depth -= char == ">"
        if depth == 0 and char not in "<>":
            kept.append(char)
    return "".join(kept).split()[-1].strip("*& \t") if "".join(kept).split() else ""


## @brief Whether a declared type IS this RAII pattern, rather than mentions it.
## @param pattern_name The pattern's declared token.
## @param type_text Raw text of a declaration's `type` field.
## @return True when the type's own name is the pattern.
## @version 1
## @dg_internal
def _raii_type_matches(pattern_name: str, type_text: str) -> bool:
    """Matching used to be `pattern.name in type_text` — a raw substring test
    over the whole type text, TEMPLATE ARGUMENTS INCLUDED. So
    `std::vector<unique_lock_stats> tally(depth_);` matched `unique_lock` and was
    recorded as an exclusive acquisition of a lock named `depth_`. That is a
    fabricated lock IDENTITY, indistinguishable from real synchronization, and
    it is the same class of error the scope-qualified identity rule exists to
    prevent — arriving through the neighbouring door.

    THE BARE TAIL IS KEPT DELIBERATELY, and requiring `std::` would be a
    regression, not a tightening. A codebase with `using namespace std;` writes
    `lock_guard<mutex> g(m);` and means it: measured on the public
    [entropic](https://github.com/tvanfossen/entropic) tree, 12 declaration sites
    are written bare. A pattern also names a CONVENTION rather than a namespace,
    so `boost::unique_lock` is a real exclusive hold and must match too. This is
    the asymmetry with `threads.DEFAULT_PY_SPAWN_PATTERNS`, whose dotted paths
    are matched against an IMPORT-RESOLVED callee: that walker can resolve the
    qualifier, and this one cannot, so equality on the unqualified tail is the
    strongest test available here rather than a laxer choice.

    A DECLARED pattern that spells a qualifier (`myns::ScopedLock`) is compared
    whole, so a repo that wants the narrower match can still ask for it.

    @brief Test a declared type's own name against a RAII pattern token.
    @return True on a match.
    @version 1
    """
    base = _base_type_name(type_text)
    if "::" in pattern_name:
        return base == pattern_name
    return base.rsplit("::", 1)[-1] == pattern_name


## @brief Record one RAII guard declaration, if the type names a lock pattern.
## @param node Declaration node.
## @param src Source bytes.
## @param patterns Pattern lookup by name.
## @param sites Accumulator.
## @return None.
## @version 3
## @dg_internal
def _visit_declaration(node: Any, src: bytes, patterns: dict, sites: list) -> None:
    """@brief Append a site for `std::lock_guard<...> g(mutex_);` and kin."""
    type_text = _text(node.child_by_field_name("type"), src)
    raii = (p for p in patterns.values() if p.form == "raii")
    pattern = next((p for p in raii if _raii_type_matches(p.name, type_text)), None)
    if pattern is None:
        return
    primitives = _primitive_names(patterns)
    for operand in _operand_names(_operand_list(node.child_by_field_name("declarator")), src) or [
        ""
    ]:
        _append_site(node, src, pattern, operand, "scoped", sites, primitives)


## Rust's `.unwrap()`/`.expect(msg)`/`.unwrap_or_else(recover)` and the `?`
## operator are how a `Result<Guard, _>` from `.lock()`/`.read()`/`.write()`
## gets down to the guard itself; parking_lot's Mutex isn't fallible at all
## and needs no unwrap. `.unwrap_or_else` is the standard poison-recovery
## idiom (`m.lock().unwrap_or_else(|e| e.into_inner())`) — verified missing
## against `tools_sqc/src/progress.rs`, whose `Mutex` guard acquisitions all
## use this form and were silently absent from the `locks` table (0 rows)
## because this function returned the `unwrap_or_else` call itself, whose
## `field` name matches no lock-method pattern, rather than peeling to the
## `.lock()` call beneath it. Capped like `call_edges._MAX_CALLEE_UNWRAP` so
## a pathological chain cannot spin.
_MAX_RUST_RESULT_UNWRAP = 4

## Method names that consume a `Result`/`Option` down to its `Ok`/`Some`
## value (discarding the error/recovery-closure side) without changing
## whether the receiver was a lock acquisition.
_RUST_RESULT_UNWRAP_METHODS = (b"unwrap", b"expect", b"unwrap_or_else")


## @brief Peel .unwrap()/.expect()/.unwrap_or_else()/`?` off a Rust expression down to its base call.
## @param node A `let_declaration`'s value expression.
## @return The innermost call_expression, or the original node if there was nothing to peel.
## @version 2
## @dg_internal
def _unwrap_rust_result(node: Any) -> Any:
    """@brief Unwrap Result/Option combinators to the call they wrap."""
    for _ in range(_MAX_RUST_RESULT_UNWRAP):
        if node is None:
            return None
        if node.type == "try_expression":
            node = next(iter(node.named_children), None)
            continue
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func is not None and func.type == "field_expression":
                field = func.child_by_field_name("field")
                if field is not None and field.text in _RUST_RESULT_UNWRAP_METHODS:
                    node = func.child_by_field_name("value")
                    continue
        return node
    return None


## @brief Record one Rust lock-guard binding, if the call names a lock method.
## @param node A `let_declaration` node.
## @param src Source bytes.
## @param patterns Pattern lookup by name.
## @param sites Accumulator.
## @return None.
## @version 1
## @dg_internal
def _visit_rust_let_binding(node: Any, src: bytes, patterns: dict, sites: list) -> None:
    """Append a site for `let g = mutex.lock().unwrap();` and kin — the Rust
    counterpart of `_visit_declaration`, keyed on a METHOD NAME
    (`lock`/`read`/`write`/...) rather than a declared guard type, since
    tree-sitter-rust names no node "declaration" for `_visit_declaration`'s
    type-name match to ever fire on.

    @brief Append a site for a Rust `let`-bound lock-guard acquisition.
    @version 1
    """
    call = _unwrap_rust_result(node.child_by_field_name("value"))
    if call is None or call.type != "call_expression":
        return
    func = call.child_by_field_name("function")
    if func is None or func.type != "field_expression":
        return
    field = func.child_by_field_name("field")
    method = _text(field, src) if field is not None else ""
    pattern = patterns.get(method)
    if pattern is None or pattern.form != "raii" or pattern.kind not in ("mutex", "shared_mutex"):
        return
    receiver = func.child_by_field_name("value")
    operand = _text(receiver, src) if receiver is not None else ""
    _append_site(call, src, pattern, operand, "scoped", sites, _primitive_names(patterns))


## @brief Record one call-form acquisition, if the callee names a lock pattern.
## @param node Call-expression node.
## @param src Source bytes.
## @param patterns Pattern lookup by name.
## @param sites Accumulator.
## @return None.
## @version 2
## @dg_internal
def _visit_call(node: Any, src: bytes, patterns: dict, sites: list) -> None:
    """@brief Append a site for `pthread_mutex_lock(&m)` and kin."""
    callee = _text(node.child_by_field_name("function"), src)
    pattern = patterns.get(callee)
    if pattern is None or pattern.form != "call":
        return
    operands = _operand_names(node.child_by_field_name("arguments"), src)
    operand = operands[pattern.operand_index] if len(operands) > pattern.operand_index else ""
    _append_site(node, src, pattern, operand, pattern.role, sites, _primitive_names(patterns))


## @brief Harvest every lock declaration/acquisition site in one file.
## @param tree Parsed tree.
## @param src_bytes Source bytes.
## @param patterns Pattern lookup by name.
## @return Rowid-free site records.
## @version 2
## @dg_internal
def _walk_lock_sites(tree: Any, src_bytes: bytes, patterns: dict) -> list[list[Any]]:
    """Rowid-free by design, like every other harvest payload, so the result
    caches against the file's content sha and re-resolves against whatever
    rowids the next build produces.

    `let_declaration` is Rust-only (neither C/C++ nor Python ever produce it),
    and `declaration`/`call_expression` are never produced by a Rust parse
    (Rust's own `.lock()`/`.read()`/`.write()` calls ARE `call_expression`
    nodes, but `_visit_call` only matches a pattern whose `form == "call"`,
    and every Rust pattern is `form == "raii"` — so it harmlessly no-ops
    there instead of double-recording the site `_visit_rust_let_binding`
    already found).

    @brief Walk one file for lock sites.
    @return List of site records.
    @version 2
    """
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "declaration":
            _visit_declaration(node, src_bytes, patterns, sites)
        elif node.type == "let_declaration":
            _visit_rust_let_binding(node, src_bytes, patterns, sites)
        elif node.type == "call_expression":
            _visit_call(node, src_bytes, patterns, sites)
    return sites


## @brief Per-file harvester for lock sites (cacheable like every other stage).
## @version 1
class _LockHarvester(Harvester):
    """Records one row per lock declaration/acquisition site.

    @brief Lock-site per-file harvester.
    @version 1
    """

    stage = STAGE_LOCKS
    # Bump when _walk_lock_sites' extraction changes.
    # 2: sites carry the L2 critical-section membership (a tenth/eleventh field)
    #    and their extent comes from `critical_sections.resolve_section`, so a
    #    payload cached by version 1 has neither the calls nor the corrected
    #    end_line and MUST NOT be served.
    # 3: RAII type matching is equality on the declared type's own name instead
    #    of a substring of the whole type text, so a payload cached by version 2
    #    may contain fabricated sites (`std::vector<unique_lock_stats>` recorded
    #    as an acquisition) that this version would never produce.
    stage_version = 3
    label = "lock sites"

    ## @brief Store the pattern map plus the manifest-derived cache key.
    ## @version 1
    ## @dg_internal
    def __init__(self, patterns_by_name: dict[str, LockPattern], extra_key: str) -> None:
        super().__init__(extra_key)
        self.patterns_by_name = patterns_by_name

    ## @brief Harvest one file's lock sites.
    ## @return List of site records.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-011
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return _walk_lock_sites(tree, src_bytes, self.patterns_by_name)


## @brief The lock stage's harvester for one declared lock vocabulary.
## @param lock_patterns Declared `locks:` section, a YAML path, or None.
## @return A Harvester keyed on the declaration's content hash.
## @version 1
## @req REQ-DDB-SCHEMA-011
def lock_harvester(lock_patterns: Path | dict | None = None) -> Harvester:
    """The ONE construction site, called once per build by gh#358's shared parse
    pass and handed to `extract_locks` — so the key the pass writes and the key the
    stage reads cannot drift, and the declaration merge (with its shadowing
    warnings) runs once.

    @brief Build this stage's harvester.
    @version 1
    """
    patterns = load_lock_patterns(lock_patterns)
    return _LockHarvester({p.name: p for p in patterns}, manifest_key(lock_patterns))


## @brief Insert (or reuse) a lock identity, returning its row id.
## @param conn Open connection.
## @param name Mutex operand name.
## @param scope Scope-qualified owner.
## @param kind Primitive kind.
## @param path_rowid Path the acquisition was seen in.
## @return The lock's row id, or None when it has no usable name.
## @version 1
## @dg_internal
def _lock_id(
    conn: sqlite3.Connection, name: str, scope: str, kind: str, path_rowid: int
) -> int | None:
    """Identity is (name, scope, kind). A site whose operand could not be read
    gets NO lock row — an unnamed lock cannot be told apart from any other
    unnamed lock, and merging them would invent shared synchronization.

    `identity_confidence` is 'high' only when the scope is known; an unscoped
    lock is still recorded, but marked 'low' so a consumer can weigh it rather
    than trusting a bare name that may recur across classes.

    @brief Resolve or create a lock identity.
    @return Lock row id, or None.
    @version 1
    """
    if not name:
        return None
    confidence = "low" if scope == SCOPE_UNKNOWN else "high"
    conn.execute(
        "INSERT OR IGNORE INTO locks "
        "(name, scope, kind, decl_path_rowid, identity_confidence, source) "
        "VALUES (?, ?, ?, ?, ?, 'ast_use')",
        (name, scope, kind, path_rowid, confidence),
    )
    row = conn.execute(
        "SELECT id FROM locks WHERE name=? AND scope=? AND kind=?", (name, scope, kind)
    ).fetchone()
    return row[0] if row else None


## @brief Persist one file's harvested lock sites.
## @param conn Open connection.
## @param path_rowid Path row the sites came from.
## @param payload Harvested site records.
## @param funcs_in_file Function extents for holder resolution.
## @param name_to_rowids Function-name index, for resolving L2 callee names.
## @return (acquisition rows inserted, membership rows inserted).
## @version 3
## @dg_internal
def _insert_sites(
    conn: sqlite3.Connection,
    path_rowid: int,
    payload: list[list[Any]],
    funcs_in_file: list[tuple[int, str, int, int]],
    name_to_rowids: dict[str, list[int]],
) -> tuple[int, int]:
    """A site whose enclosing function cannot be resolved is DROPPED: an
    acquisition with no holder answers no question anyone asks, and inventing
    a holder would be worse.

    `confidence` now carries what `ACQ_STRENGTH` says it carries — how well the
    EXTENT resolved. It used to be written as `'high' if lock_id is not None`,
    which is IDENTITY confidence and was already recorded, correctly, in
    `locks.identity_confidence`; the column named for the extent said nothing
    about the extent, and every unbounded acquisition in a well-named repo
    reported 'high'.

    @brief Insert acquisitions, their lock identities, and their L2 membership.
    @return (acquisition rows inserted, membership rows inserted).
    @version 3
    """
    from .call_edges import _ast_caller_at_line

    inserted = 0
    members = 0
    for record in payload:
        holder = _ast_caller_at_line(funcs_in_file, record[3])
        if holder is None:
            continue
        added, acquisition_id = _insert_one_site(conn, path_rowid, record, holder)
        inserted += added
        if acquisition_id is not None:
            members += insert_section_calls(conn, acquisition_id, record[10], name_to_rowids)
    return inserted, members


## @brief Insert one acquisition row and return its id.
## @param conn Open connection.
## @param path_rowid Path row the site came from.
## @param record One harvested site record.
## @param holder Enclosing function's memberdef rowid.
## @return (rows inserted, the acquisition's id or None).
## @version 1
## @dg_internal
def _insert_one_site(
    conn: sqlite3.Connection, path_rowid: int, record: list[Any], holder: int
) -> tuple[int, int | None]:
    """The id is re-SELECTed on the UNIQUE key rather than read from
    `lastrowid`: the statement is `INSERT OR IGNORE`, so a duplicate site
    inserts nothing and `lastrowid` then reports whatever the connection last
    inserted — a DIFFERENT acquisition, which would file this site's membership
    under someone else's lock.

    @brief Insert one acquisition and resolve its row id.
    @version 1
    """
    pattern_name, operand, scope, start, end, form, kind, mode, role, confidence = record[:10]
    lock_id = _lock_id(conn, operand, scope, kind, path_rowid)
    added = conn.execute(
        "INSERT OR IGNORE INTO lock_acquisitions "
        "(lock_id, holder_rowid, path_rowid, form, role, mode, start_line, end_line, "
        " pattern_name, declared, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
        (lock_id, holder, path_rowid, form, role, mode, start, end, pattern_name, confidence),
    ).rowcount
    row = conn.execute(
        "SELECT id FROM lock_acquisitions WHERE holder_rowid=? AND start_line=? AND pattern_name=?",
        (holder, start, pattern_name),
    ).fetchone()
    return added, (row[0] if row else None)


## @brief Harvest lock declarations, acquisitions and critical-section members.
## @param db_path Database being built.
## @param repo_root Working tree to scan.
## @param lock_patterns Declared `locks:` section, a YAML path, or None.
## @param cache Live index cache, or None.
## @param harvester Pre-built harvester from the shared parse pass; built here when omitted.
## @return None.
## @version 4
## @req REQ-DDB-SCHEMA-011
def extract_locks(
    db_path: Path,
    repo_root: Path,
    lock_patterns: Path | dict | None = None,
    cache: IndexCache | None = None,
    harvester: Harvester | None = None,
) -> None:
    """Runs after the call-edge layers so function extents exist for holder
    resolution. The tables are created unconditionally, so a repo with no locks
    — or a build without tree_sitter — yields empty tables rather than absent
    ones, and R2/R4 never branch on existence.

    The function-name index that Layer 3 builds for call edges is reused here to
    resolve L2's callee names, so an `critical_section_calls.callee_rowid` and a
    `call_edges.callee_rowid` for the same site agree by construction rather
    than by two independent lookups that could drift.

    `harvester` is the one gh#358's shared parse pass already built and warmed the
    cache with. Passing the OBJECT rather than rebuilding from `lock_patterns` is
    what makes the two cache keys equal by construction; rebuilding here would also
    re-run the declaration merge and its warnings a second time. Omitted (every
    caller outside the pipeline), it is built here exactly as before.

    @brief Populate locks + lock_acquisitions + critical_section_calls.
    @version 4
    """
    from .call_edges import _build_function_indexes

    conn = sqlite3.connect(str(db_path))
    _ensure_lock_tables(conn)
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.info("locks: tree_sitter unavailable — skipping (tables still created)")
        conn.commit()
        conn.close()
        return
    name_to_rowids, file_funcs = _build_function_indexes(conn)
    harvester = harvester or lock_harvester(lock_patterns)
    inserted = 0
    members = 0
    for path_rowid, payload in run_harvest(conn, repo_root, harvester, ts_classes, cache):
        added, member_rows = _insert_sites(
            conn, path_rowid, payload, file_funcs.get(path_rowid, []), name_to_rowids
        )
        inserted += added
        members += member_rows
    conn.commit()
    _log_lock_summary(conn, inserted, members)
    conn.close()


## @brief Log what the lock layer found, including L2's coverage.
## @param conn Open connection to the populated database.
## @param inserted Acquisition rows inserted.
## @param members Membership rows inserted.
## @return None.
## @version 1
## @dg_internal
def _log_lock_summary(conn: sqlite3.Connection, inserted: int, members: int) -> None:
    """Reports the UNRESOLVED-extent count explicitly. "0 membership rows" is
    ambiguous between a repo whose sections are empty and a detector that could
    not bound a single one — the same "no rows is a claim about the DETECTOR"
    trap that made this project record an empty dataflow layer as a correct
    negative when the accessors were simply macros.

    @brief Summarize the lock layer's L1 and L2 findings.
    @version 1
    """
    locks_seen = conn.execute("SELECT COUNT(*) FROM locks").fetchone()[0]
    unscoped = conn.execute(
        "SELECT COUNT(*) FROM locks WHERE scope = ?", (SCOPE_UNKNOWN,)
    ).fetchone()[0]
    unresolved = conn.execute(
        "SELECT COUNT(*) FROM lock_acquisitions WHERE confidence = ?", (EXTENT_UNRESOLVED,)
    ).fetchone()[0]
    logger.info(
        "locks: %d distinct locks (%d unscoped), %d acquisition sites "
        "(%d with an unresolved extent), %d critical-section calls",
        locks_seen,
        unscoped,
        inserted,
        unresolved,
        members,
    )


## The pairing that identifies a lock primitive without guessing a vocabulary. A repo's own
## primitive is not recognisable from its NAME — `bsp_lock_take`, `k_mutex_lock` and
## `mbedtls_mutex_lock` share no token — but a lock primitive is almost always half of an
## ACQUIRE/RELEASE PAIR, and the pair is structural.
_LOCK_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_lock", "_unlock"),
    ("_take", "_give"),
    ("_acquire", "_release"),
    ("_enter", "_exit"),
)


## @brief Called acquire/release pairs that no active lock pattern covers.
## @param conn Open connection to the built index.
## @param patterns The lock patterns this build ran with.
## @return Sorted acquire-side names, first party first, each paired name it was matched on.
## @version 1
## @req REQ-DDB-CONFIG-007
def detect_undeclared_lock_primitives(
    conn: sqlite3.Connection, patterns: list[LockPattern]
) -> list[tuple[str, str]]:
    """THE MEASURED GAP (gh#385). On mbedtls the lock layer held ONE identity — `mutex->mutex`,
    scope unknown, confidence low — for a repository with five named global mutexes and 38 lock
    sites, and a graded agent copied that number into its answer as "one first-party mutex
    identity resolved with 1 acquisition". Every acquisition goes through the function POINTER
    `mbedtls_mutex_lock`, which is not a built-in primitive, so the detector only ever saw
    `pthread_mutex_lock(&mutex->mutex)` inside the single wrapper.

    DECLARING IT IS THE FIX, and it works: `locks: [{name: mbedtls_mutex_lock, form: call,
    kind: mutex, role: acquire, operand_index: 0}]` takes the layer from 1 identity / 1
    acquisition to 10 / 46, with real names (`mbedtls_threading_gmtime_mutex`, `debug_mutex`,
    `ctx->mutex`, `heap.mutex`). That is the same answer the `STORE_SET_*` accessors got: the
    layer was empty because the detector had no way to look, not because the repo has no locks.

    SO THE DEFECT IS THAT NOTHING TOLD THE OWNER TO DECLARE IT. `detect_undeclared_accessor_families`
    exists for exactly this reason one layer over, and the lock layer had no counterpart — it
    reported a confident `1` instead of a hint. Purely advisory: this never fabricates an
    acquisition.

    PAIRED, NOT NAME-SNIFFED. A single name containing "lock" proves nothing — `spinlock_t`,
    `unlock_reason`, `lock_free_queue` all contain it. What identifies a primitive is that
    BOTH halves of an acquire/release pair are CALLED in the same index, which is a property of
    the code rather than of a naming fashion. `_take`/`_give` catches FreeRTOS, `_enter`/`_exit`
    catches Zephyr-style and CMSIS-style, and a repo whose pair this misses still declares
    explicitly — a missed hint costs nothing, while a false hint costs an operator real time,
    which is the asymmetry `AccessorFamily` records.

    @brief Suggest acquire/release pairs a build should declare as lock primitives.
    @return (acquire name, release name) pairs, sorted.
    @version 1
    """
    ## READ FROM `memberdef`, NOT FROM CALL SITES, and the reason is the defect itself: the
    ## primitive is a function POINTER, so the fnptr layer resolves each call to the BOUND
    ## implementation (`threading_mutex_lock_pthread`) and the pointer's own name never appears
    ## as a callee. No table carries unresolved callee names — `critical_section_calls` has one
    ## but only inside an already-detected critical section, which is exactly what is missing
    ## here. So the pair is looked for among indexed NAMES, whatever kind they are: mbedtls's
    ## halves are `variable` rows, and a repo whose primitive is a real function has them as
    ## `function` rows.
    covered = {p.name.lower() for p in patterns}
    called = {row[0] for row in conn.execute("SELECT DISTINCT name FROM memberdef WHERE name<>''")}
    found: list[tuple[str, str]] = []
    for name in sorted(called):
        lowered = name.lower()
        if lowered in covered:
            continue
        for acquire_suffix, release_suffix in _LOCK_SUFFIXES:
            if not lowered.endswith(acquire_suffix):
                continue
            partner = name[: -len(acquire_suffix)] + release_suffix
            if partner in called:
                found.append((name, partner))
            break
    return found
