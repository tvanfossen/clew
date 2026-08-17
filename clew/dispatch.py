# SPDX-License-Identifier: MIT
"""The indirect-dispatch DECLARATION — a repo's own map of its indirections.

The static graph recovers a relationship only when both endpoints are named at
the site. A call edge needs the callee named at the call site; a shared-key edge
needs the key named at the accessor site. Every real firmware/robotics repo
routes some of these through an indirection that hides one endpoint, and there
the graph simply stops:

Every concrete identifier below is INVENTED and ILLUSTRATIVE. The names exist only
to give a sentence about an indirection two named endpoints — do not go looking for
them in any real codebase. The numbers are real and measured; the names are not.

  * **virtual/interface** — `port_.transmit(pkt)` where `port_` is an
    `hw::ILinkPort&`. The concrete implementor is chosen at construction and is
    invisible at the call site, so an interface-HAL C++ codebase's causal chains all
    break at their HAL seam and `external_boundaries` reads 0 — not because the
    terminus detector failed but because it only knew the OTHER terminus kind.
  * **function-pointer table** — a registry maps a key to a handler pointer and
    invokes `table[i](key)`. The callee is a runtime value, so the whole
    dispatched sub-graph reads as unreachable — the liveness orphans are the
    trampolines, the broker, and everything they invoke.
  * **argument-keyed wrapper** — `store_bool_on_delta(DM_KEY_X, v)`, where the
    key is an ARGUMENT to a generic helper rather than baked into the accessor's
    name. Neither the literal-pattern nor the name-embedded inference matches, so
    the key has no dataflow at all.

All three are CONVENTIONS. A C++ codebase's broker fan-out, an RTOS repo's
queue-of-callbacks and a C library's dispatch tables are three different shapes
of one problem, so clew must not bake in any of them — it reads a manifest the
target repo owns, exactly as the shared-key / thread / lock conventions already
work. No declaration means no synthetic edges, which on a repo with no
indirection convention is a correct negative, not a gap.

Declared as the `dispatch` section of `.clew.yaml` (or a standalone file via
`--dispatch`; both routes feed this one parser)::

    dispatch:
      interfaces:
        - interface: ILinkPort         # abstract type named at the call site
          binds: SerialLinkPort        # concrete implementor, resolved in-index
          methods: [transmit]          # optional; default = every override pair
          boundary: true               # optional; ALSO record a terminus here
      dispatch_tables:
        - register_via: register_dispatcher   # the call that stores a handler
          handler_arg_index: 0                # which argument is the handler
          dispatch_via: Broker::fan           # the function that invokes them
      shared_key_wrappers:
        - pattern: store_bool_on_delta
          key_arg_index: 0
          direction: write
      key_alias_prefixes: ["DM_KEY_"]   # optional; overrides the ingot default

SHAPE NOTE — `dispatch_tables` deliberately departs from the SPEC's illustrative
`container_type` / `handler_field` keys. Those name the DATA STRUCTURE but
neither endpoint of the edge that has to be emitted; deriving the invoking
function from a container type means finding whoever iterates that container,
which is the very indirection that defeated static analysis to begin with.
`register_via` + `dispatch_via` name both endpoints directly, which is the
minimum an edge needs and the maximum an author can state without ambiguity.

FAIL CLOSED on anything malformed. A declaration is a claim about how the system
is wired; a typo that degrades to "declared nothing" produces a build that
silently keeps the gap the author was trying to close, and looks identical to a
repo that never declared anything.

@brief Parse a target repo's declared indirect-dispatch conventions.
@version 2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._common import logger
from .declaration import SECTION_DISPATCH
from .vocabulary import KEY_DIRECTION, DeclarationError, declaration_origin

## The three independently-optional sections of the manifest.
KEY_INTERFACES = "interfaces"
KEY_TABLES = "dispatch_tables"
KEY_WRAPPERS = "shared_key_wrappers"
## Optional: overrides the built-in enum-key alias prefixes (see shared_key_edges).
KEY_ALIAS_PREFIXES = "key_alias_prefixes"

## Every key each level of the document may carry. Anything else is REFUSED.
##
## Without this, the module's own fail-closed promise had a hole in exactly the
## shape it warns about: `_entries` returns [] for an ABSENT section, so
## `interface:`/`dispatch_table:`/`shared_key_wrapper:` — every plausible
## singular/plural slip — parsed to an empty manifest and built green while the
## author's declaration did nothing. The same applies one level down: `key_arg_idx`
## for `key_arg_index` silently defaults the key to argument 0, which does not
## produce "no dataflow" but the WRONG dataflow, from a typo.
_DOCUMENT_KEYS = frozenset({KEY_INTERFACES, KEY_TABLES, KEY_WRAPPERS, KEY_ALIAS_PREFIXES})
_INTERFACE_KEYS = frozenset({"interface", "binds", "methods", "boundary"})
_TABLE_KEYS = frozenset({"register_via", "handler_arg_index", "dispatch_via"})
_WRAPPER_KEYS = frozenset({"pattern", "key_arg_index", "direction"})


## @brief Refuse a mapping carrying any key outside its allowed set.
## @param mapping The declared mapping (a document or one entry).
## @param allowed The keys this level of the schema defines.
## @param owner Where it was declared, for the error message.
## @return None.
## @version 1
## @dg_internal
def _reject_unknown(mapping: dict, allowed: frozenset[str], owner: str) -> None:
    """Names the offending keys AND the allowed set, so the fix is mechanical —
    the same triple every other fail-closed refusal in the package carries.

    @brief Reject unknown keys at one level of the dispatch schema.
    @version 1
    """
    unknown = sorted(str(k) for k in mapping if k not in allowed)
    if unknown:
        raise DeclarationError(
            f"{owner}: unknown key(s) {', '.join(repr(k) for k in unknown)} "
            f"— allowed: {', '.join(sorted(allowed))}"
        )


## @brief One declared interface→implementor binding.
## @version 1
class InterfaceBinding:
    """Which concrete type backs an injected abstract seam.

    `methods` narrows the binding to named methods; empty means every method the
    implementor overrides. `boundary` marks the interface call as an out-of-repo
    sink — a SECOND terminus kind alongside the forwarded-callback one, for the
    case where the real implementor is not in the index at all. An entry may
    carry `binds`, `boundary`, or both: a HAL interface commonly has one in-repo
    fake and one out-of-repo driver.

    @brief A declared interface→implementor binding.
    @version 1
    """

    __slots__ = ("binds", "boundary", "interface", "methods")

    ## @brief Store the interface name, implementor, method filter, and boundary flag.
    ## @param interface Abstract type named at the call site.
    ## @param binds Concrete implementor, or "" when only a boundary is declared.
    ## @param methods Method names to restrict to; empty means all overrides.
    ## @param boundary True when the interface call is itself an external sink.
    ## @version 1
    ## @dg_internal
    def __init__(
        self, interface: str, binds: str, methods: tuple[str, ...], boundary: bool
    ) -> None:
        self.interface = interface
        self.binds = binds
        self.methods = methods
        self.boundary = boundary


## @brief One declared function-pointer dispatch table.
## @version 1
class DispatchTable:
    """A registration call that stores a handler pointer, plus the function that
    later invokes the stored handlers.

    Both endpoints are named because an edge needs both. A repo whose table is
    read from two places declares two entries sharing one `register_via`.

    @brief A declared fnptr registration/dispatch pair.
    @version 1
    """

    __slots__ = ("dispatch_via", "handler_arg_index", "register_via")

    ## @brief Store the registrar name, handler argument position, and dispatcher.
    ## @param register_via Callee whose call sites register a handler.
    ## @param handler_arg_index 0-indexed position of the handler argument.
    ## @param dispatch_via Function whose body invokes the registered handlers.
    ## @version 1
    ## @dg_internal
    def __init__(self, register_via: str, handler_arg_index: int, dispatch_via: str) -> None:
        self.register_via = register_via
        self.handler_arg_index = handler_arg_index
        self.dispatch_via = dispatch_via


## @brief One declared argument-keyed shared-key wrapper.
## @version 1
class KeyWrapper:
    """A generic helper whose shared KEY is an argument rather than part of its
    name. Exactly the existing `--shared-key-patterns` argument convention,
    surfaced here so the whole indirection story lives in one manifest.

    @brief A declared argument-keyed accessor wrapper.
    @version 1
    """

    __slots__ = ("direction", "key_arg_index", "pattern")

    ## @brief Store the helper name glob, key argument position, and direction.
    ## @param pattern Callee-name glob the helper matches.
    ## @param key_arg_index 0-indexed position of the key argument.
    ## @param direction 'write' or 'read' — which accessor list this joins.
    ## @version 1
    ## @dg_internal
    def __init__(self, pattern: str, key_arg_index: int, direction: str) -> None:
        self.pattern = pattern
        self.key_arg_index = key_arg_index
        self.direction = direction


## @brief A repo's parsed indirect-dispatch declaration.
## @version 1
class DispatchManifest:
    """The three sections plus the optional key-alias override, already
    validated. Empty when the repo declares nothing — the universal case today,
    and the one every existing build must keep producing byte-for-byte.

    @brief Parsed `dispatch` declaration.
    @version 1
    """

    __slots__ = ("interfaces", "key_alias_prefixes", "tables", "wrappers")

    ## @brief Store the parsed sections.
    ## @param interfaces Declared interface bindings.
    ## @param tables Declared fnptr dispatch tables.
    ## @param wrappers Declared argument-keyed key wrappers.
    ## @param key_alias_prefixes Declared enum-key prefix overrides, or ().
    ## @version 1
    ## @dg_internal
    def __init__(
        self,
        interfaces: list[InterfaceBinding],
        tables: list[DispatchTable],
        wrappers: list[KeyWrapper],
        key_alias_prefixes: tuple[str, ...],
    ) -> None:
        self.interfaces = interfaces
        self.tables = tables
        self.wrappers = wrappers
        self.key_alias_prefixes = key_alias_prefixes

    ## @brief True when the declaration would produce nothing.
    ## @return True when all three sections are empty.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-004
    def is_empty(self) -> bool:
        """@brief True when nothing was declared.

        @version 1
        """
        return not (self.interfaces or self.tables or self.wrappers)


## @brief An empty manifest, for the (universal, today) undeclared case.
## @return A DispatchManifest with every section empty.
## @version 1
## @req REQ-DDB-SCHEMA-004
def empty_manifest() -> DispatchManifest:
    """Constructed rather than shared as a module constant: the sections are
    mutable lists, and a shared instance is one accidental `.append` away from
    leaking one build's declaration into the next.

    @brief Build a fresh empty manifest.
    @version 1
    """
    return DispatchManifest([], [], [], ())


## @brief Read a required non-empty string field, failing closed when absent.
## @param entry The declaration entry mapping.
## @param field Field name to read.
## @param owner Where the entry was declared, for the error message.
## @return The field's string value.
## @version 1
## @dg_internal
def _required(entry: dict, field: str, owner: str) -> str:
    """A missing required field is refused rather than defaulted. There is no
    honest default for "which interface" or "which registrar" — inventing one
    would silently bind a call graph the author never described.

    @brief Read a mandatory declaration field.
    @version 1
    """
    value = str(entry.get(field, "") or "").strip()
    if not value:
        raise DeclarationError(f"{owner}: missing required field {field!r}")
    return value


## @brief Coerce one section to a list of mapping entries, failing closed.
## @param doc The whole parsed dispatch document.
## @param name Section name.
## @param origin Where the document came from, for error messages.
## @return The section's entries, or [] when the section is absent.
## @version 1
## @dg_internal
def _entries(doc: dict, name: str, origin: str) -> list[dict]:
    """A section that is present but not a list of mappings is a typo, not a
    declaration — refused, because degrading it to "declared nothing" leaves the
    author with a green build and the gap they were closing still open.

    @brief Read one section as a list of entry mappings.
    @version 1
    """
    raw = doc.get(name)
    if raw is None:
        return []
    if not isinstance(raw, list) or any(not isinstance(e, dict) for e in raw):
        raise DeclarationError(f"{origin}: {name} must be a list of mappings")
    return raw


## @brief Parse one `interfaces:` entry.
## @param entry The entry mapping.
## @param origin Where it was declared.
## @return The validated InterfaceBinding.
## @version 1
## @dg_internal
def _interface_entry(entry: dict, origin: str) -> InterfaceBinding:
    """`binds` is optional only when `boundary: true` — an entry with neither
    names an interface and then asks for nothing, which is far more likely a
    half-finished edit than an intent.

    @brief Validate one declared interface binding.
    @version 2
    """
    _reject_unknown(entry, _INTERFACE_KEYS, f"{origin}: {KEY_INTERFACES} entry")
    interface = _required(entry, "interface", origin)
    owner = f"{origin}: interface {interface!r}"
    binds = str(entry.get("binds", "") or "").strip()
    boundary = bool(entry.get("boundary", False))
    if not binds and not boundary:
        raise DeclarationError(
            f"{owner}: declares neither 'binds' nor 'boundary: true' — it would do nothing"
        )
    methods = tuple(str(m) for m in (entry.get("methods") or []) if str(m))
    return InterfaceBinding(interface, binds, methods, boundary)


## @brief Parse one `dispatch_tables:` entry.
## @param entry The entry mapping.
## @param origin Where it was declared.
## @return The validated DispatchTable.
## @version 1
## @dg_internal
def _table_entry(entry: dict, origin: str) -> DispatchTable:
    """Both endpoints are required. Knowing only where handlers are registered
    tells us what the table holds but not who calls it, and an edge needs a
    caller — see the module docstring on the SPEC's illustrative shape.

    @brief Validate one declared fnptr dispatch table.
    @version 2
    """
    _reject_unknown(entry, _TABLE_KEYS, f"{origin}: {KEY_TABLES} entry")
    register_via = _required(entry, "register_via", origin)
    owner = f"{origin}: dispatch table {register_via!r}"
    dispatch_via = _required(entry, "dispatch_via", owner)
    return DispatchTable(register_via, int(entry.get("handler_arg_index", 0)), dispatch_via)


## @brief Parse one `shared_key_wrappers:` entry.
## @param entry The entry mapping.
## @param origin Where it was declared.
## @return The validated KeyWrapper.
## @version 1
## @dg_internal
def _wrapper_entry(entry: dict, origin: str) -> KeyWrapper:
    """`direction` is validated against the vocabulary: a typo filed as the
    opposite role inverts the dataflow the entry exists to reveal, and would
    still build green.

    @brief Validate one declared argument-keyed wrapper.
    @version 2
    """
    _reject_unknown(entry, _WRAPPER_KEYS, f"{origin}: {KEY_WRAPPERS} entry")
    pattern = _required(entry, "pattern", origin)
    owner = f"{origin}: key wrapper {pattern!r}"
    direction = KEY_DIRECTION.validated(
        str(entry.get("direction", "write")), owner=owner, field="direction"
    )
    return KeyWrapper(pattern, int(entry.get("key_arg_index", 0)), direction)


## @brief Read the parsed document behind a path or an already-parsed mapping.
## @param source A manifest path, a `.clew.yaml` section mapping, or None.
## @return The document mapping, or None when there is nothing to parse.
## @version 3
## @dg_internal
def _document(source: Path | dict | None) -> dict | None:
    """Both delivery routes converge here, so a standalone `--dispatch` file and
    the `.clew.yaml` section are guaranteed to have exactly one format and one
    set of error messages.

    @brief Resolve a manifest source to its parsed mapping.
    @version 3
    """
    if source is None:
        return None
    if isinstance(source, dict):
        return source
    import yaml

    data = yaml.safe_load(Path(source).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DeclarationError(f"{source}: dispatch manifest must contain a mapping")
    return data


## @brief Parse a repo's declared indirect-dispatch conventions.
## @param source A `--dispatch` path, the `.clew.yaml` `dispatch` section, or None.
## @return The parsed manifest; empty when nothing is declared.
## @version 1
## @req REQ-DDB-SCHEMA-004
def load_dispatch_manifest(source: Path | dict | None) -> DispatchManifest:
    """Undeclared is the norm: no repo has written a dispatch declaration yet, so
    this returns an empty manifest and the pipeline emits nothing. Anything
    malformed RAISES rather than degrading, because a silently-ignored
    declaration is indistinguishable from never having written one — including a
    misspelled SECTION name, which is the shape that would otherwise slip
    through (see `_reject_unknown`).

    @brief Load and validate the dispatch declaration.
    @version 2
    """
    doc = _document(source)
    if doc is None:
        return empty_manifest()
    origin = declaration_origin(source, SECTION_DISPATCH)
    _reject_unknown(doc, _DOCUMENT_KEYS, origin)
    manifest = DispatchManifest(
        [_interface_entry(e, origin) for e in _entries(doc, KEY_INTERFACES, origin)],
        [_table_entry(e, origin) for e in _entries(doc, KEY_TABLES, origin)],
        [_wrapper_entry(e, origin) for e in _entries(doc, KEY_WRAPPERS, origin)],
        tuple(str(p) for p in (doc.get(KEY_ALIAS_PREFIXES) or []) if str(p)),
    )
    if not manifest.is_empty():
        logger.info(
            "dispatch: %s declares %d interface binding(s), %d dispatch table(s), "
            "%d key wrapper(s)",
            origin,
            len(manifest.interfaces),
            len(manifest.tables),
            len(manifest.wrappers),
        )
    return manifest


## @brief Render the declared key wrappers as a shared-key patterns document.
## @param manifest The parsed dispatch manifest.
## @return A `{writers, readers, key_alias_prefixes}` mapping, or None when nothing applies.
## @version 1
## @req REQ-DDB-SCHEMA-004
def shared_key_document(manifest: DispatchManifest) -> dict | None:
    """`shared_key_wrappers` IS the argument-keyed half of the shared-key
    manifest, so it is translated into that exact entry shape rather than given a
    second parser. One format, one matcher, two places an author may write it.

    Returns None when there is nothing to contribute, so the caller can leave the
    shared-key stage's inputs — and therefore its cache key — untouched.

    @brief Translate declared wrappers into shared-key writer/reader entries.
    @version 1
    """
    if not manifest.wrappers and not manifest.key_alias_prefixes:
        return None
    doc: dict[str, Any] = {"writers": [], "readers": []}
    for wrapper in manifest.wrappers:
        bucket = "writers" if wrapper.direction == "write" else "readers"
        doc[bucket].append({"pattern": wrapper.pattern, "key_arg_index": wrapper.key_arg_index})
    if manifest.key_alias_prefixes:
        doc[KEY_ALIAS_PREFIXES] = list(manifest.key_alias_prefixes)
    return doc
