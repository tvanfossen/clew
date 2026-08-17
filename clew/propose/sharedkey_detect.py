# SPDX-License-Identifier: MIT
"""Detect key-in-the-NAME accessor families from CALL SITES.

The corpus choice is the whole design. The build-time diagnostic
(`shared_key_edges.detect_undeclared_accessor_families`) reads
`SELECT DISTINCT name FROM memberdef`, which is structurally blind to the one
convention that actually pays: on a C/POSIX library `STORE_SET_*`/`STORE_GET_*`
are MACROS — 1093 call sites, ZERO memberdef rows. That diagnostic keeps its
build-time advisory role; this detector uses a different corpus and a different
gate, and the two are allowed to disagree.

Three filters, in order, and each removes a specific measured failure:

**The verb must sit at a separator or a case boundary.** Without it, `set`
inside `update_settings_*` becomes a family — 57% of one design pass's "negative
findings" were the tail of the word "settings", plus `offset_`, `reset_`,
`tcset`/`tcget`, `cfset`.

**Arity.** A name-keyed setter takes exactly one argument and a getter none,
because the key is in the NAME. Measured: `STORE_SET_`=[1]/`GET_`=[0] pass;
`DataModel_Set`=[1,2] (the `...ByKey` dispatchers, whose key is a VARIABLE),
`Store_Set`=[0,1,3], `IntegerStorage_Set`=[2] and a third repo's
`drv_Core_Range_set_`=[2] all fail. This single gate preserves every true
family in the reference set and kills every fabricated one.

**Longest prefix, never shortest.** `DataModel_Set_<KEY>` and
`DataModel_SetStringByKey` split at DIFFERENT boundaries and are therefore
different families. Canonicalising them to the common `DataModel_Set` merges a
44-key real family with a 2-key dispatcher fragment and the merged arity then
rejects both — deleting the codebase's actual data model.

@brief Accessor-family detection for `shared_key_patterns`.
@version 1
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .scanning import AccessorSite

## A name-keyed setter takes exactly the key's value; a getter takes nothing.
## Anything else keys by ARGUMENT and is deliberately out of scope (see the
## `NOT DETECTED` note the report emits, and clew task #37).
WRITER_ARITY = frozenset({1})
READER_ARITY = frozenset({0})

## A pair must share this many keys, over this many attributed call sites,
## before it is worth measuring. Below it, a "family" is two coincidentally
## similar function names.
MIN_SHARED_KEYS = 2
MIN_PAIR_SITES = 4

_VERBS = ("set", "get")


## @brief One accessor name split into its family prefix and its key.
## @version 1
@dataclass(frozen=True)
class Split:
    """`stem` is the prefix with the verb blanked out, so a writer family and
    its reader counterpart hash to the same value: `STORE_SET_` and
    `STORE_GET_` both stem to `DATAMODEL_\\x00_`.

    @brief An accessor name decomposed into prefix / key / verb / stem.
    @version 1
    """

    prefix: str
    key: str
    verb: str
    stem: str


## @brief Split an accessor-shaped name into its family prefix and key.
## @param name The callee name at a call site.
## @return The Split, or None when the name is not accessor-shaped.
## @version 1
## @req REQ-DDB-CONFIG-001
def split_accessor(name: str) -> Split | None:
    """Takes the FIRST qualifying verb occurrence, not the last: in a
    hypothetical `A_SET_B_GET_C` the family is `A_SET_` writing the key
    `B_GET_C`, and a greedy match would invert writer and reader.

    @brief Decompose one callee name into an accessor family + key.
    @version 1
    """
    lowered = name.lower()
    found: Split | None = None
    index = 0
    while found is None and index >= 0:
        index = _next_verb(lowered, index)
        if index >= 0:
            found = _split_at(name, index)
            index += 1
    return found


## @brief Position of the next `set`/`get` occurrence at or after `start`.
## @param lowered The lowercased name.
## @param start Index to search from.
## @return The occurrence index, or -1 when there is none.
## @version 1
## @dg_internal
def _next_verb(lowered: str, start: int) -> int:
    """@brief Find the next set/get occurrence in a lowercased name."""
    positions = [pos for pos in (lowered.find(v, start) for v in _VERBS) if pos >= 0]
    return min(positions) if positions else -1


## @brief Split a name at one verb occurrence, if both boundaries hold.
## @param name The original (cased) name.
## @param index Index of the three-letter verb.
## @return The Split, or None when this occurrence is not a family boundary.
## @version 1
## @dg_internal
def _split_at(name: str, index: int) -> Split | None:
    """@brief Test one verb occurrence's leading token and both boundaries."""
    after = index + 3
    if index == 0 or not _starts_at_boundary(name, index):
        return None
    prefix_end, key_start = _key_boundary(name, after)
    if key_start <= 0 or key_start >= len(name):
        return None
    prefix = name[:prefix_end]
    return Split(
        prefix=prefix,
        key=name[key_start:],
        verb=name[index:after].lower(),
        stem=name[:index] + "\x00" + name[after:prefix_end],
    )


## @brief Whether the verb starts at a separator or a camel-case boundary.
## @param name The original (cased) name.
## @param index Index of the verb.
## @return True when the character before the verb ends a token.
## @version 1
## @dg_internal
def _starts_at_boundary(name: str, index: int) -> bool:
    """@brief Test the verb's leading boundary."""
    before = name[index - 1]
    return before == "_" or (name[index].isupper() and (before.islower() or before.isdigit()))


## @brief Where the family prefix ends and the key begins, after the verb.
## @param name The original (cased) name.
## @param after Index just past the verb.
## @return (prefix end, key start); (0, 0) when no key follows at a boundary.
## @version 2
## @dg_internal
def _key_boundary(name: str, after: int) -> tuple[int, int]:
    """A separator is consumed INTO the prefix (`STORE_SET_` + `WIFI_...`)
    so the emitted `name_prefix` is exactly what the runtime matcher strips. A
    camel boundary leaves the prefix at the verb (`Store_Set` + `AreaData`).

    @brief Locate the key after the verb.
    @version 1
    """
    if after >= len(name):
        return 0, 0
    if name[after] == "_":
        return after + 1, after + 1
    return (after, after) if (name[after].isupper() or name[after].isdigit()) else (0, 0)


## @brief One accessor family: a prefix, its keys, and its call sites.
## @version 1
@dataclass(frozen=True)
class Family:
    """`sites` are IN-SCOPE call sites (what the pipeline can attribute);
    `out_of_scope` are the rest, kept only to warn that widening the index would
    change the answer.

    @brief An accessor family harvested from call sites.
    @version 1
    """

    prefix: str
    verb: str
    stem: str
    keys: frozenset[str]
    sites: tuple[AccessorSite, ...]
    out_of_scope: tuple[AccessorSite, ...]

    ## @brief The distinct argument counts observed at this family's call sites.
    ## @return Frozenset of in-scope call-site arities.
    ## @version 1
    ## @req REQ-DDB-CONFIG-001
    def arities(self) -> frozenset[int]:
        """@brief Observed arities across the family's in-scope call sites."""
        return frozenset(site.argc for site in self.sites)


## @brief Group accessor-shaped call sites into families by prefix.
## @param sites Every accessor-shaped call site (in and out of scope).
## @return Prefix -> Family, for families with at least one in-scope call site.
## @version 1
## @req REQ-DDB-CONFIG-001
def accessor_families(sites: Sequence[AccessorSite]) -> dict[str, Family]:
    """@brief Fold accessor call sites into per-prefix families."""
    acc: dict[str, dict] = {}
    for site in sites:
        split = split_accessor(site.callee)
        if split is None:
            continue
        bucket = acc.setdefault(
            split.prefix,
            {"verb": split.verb, "stem": split.stem, "keys": set(), "in": [], "out": []},
        )
        bucket["keys"].add(split.key)
        bucket["in" if site.in_scope else "out"].append(site)
    return {
        prefix: Family(
            prefix=prefix,
            verb=data["verb"],
            stem=data["stem"],
            keys=frozenset(data["keys"]),
            sites=tuple(data["in"]),
            out_of_scope=tuple(data["out"]),
        )
        for prefix, data in acc.items()
        if data["in"]
    }


## @brief Whether every in-scope call site of a family has the expected arity.
## @param family The family to test.
## @param expect The allowed arity set (WRITER_ARITY or READER_ARITY).
## @return True when the family's observed arities are exactly the expected set.
## @version 1
## @req REQ-DDB-CONFIG-001
def arity_consistent(family: Family, expect: frozenset[int]) -> bool:
    """@brief Apply the arity gate to one family."""
    return family.arities() == expect


## @brief One writer/reader family pair that passed the structural gates.
## @version 1
@dataclass(frozen=True)
class Pair:
    """@brief A writer family, its reader counterpart, and their shared keys.

    @version 1
    """

    writer: Family
    reader: Family
    shared_keys: frozenset[str]


## @brief Every arity-consistent writer/reader pairing, thresholds not yet applied.
## @param families Every harvested family, by prefix.
## @return Candidate pairs, largest writer family first.
## @version 1
## @req REQ-DDB-CONFIG-001
def candidate_pairs(families: dict[str, Family]) -> list[Pair]:
    """Split out from `pair_families` so the evidence thresholds can be reported
    on rather than applied invisibly: a family that passes arity and then falls
    below the shared-key floor used to be dropped here with no trace, which is the
    one thing a reader cannot recover from — on the demobot fixture that silently
    swallowed its ENTIRE data model, whose punchline is that exactly one key is
    both written and read.

    @brief Pair writer families with reader families sharing a stem.
    @version 1
    """
    readers = {
        fam.stem: fam
        for fam in families.values()
        if fam.verb == "get" and arity_consistent(fam, READER_ARITY)
    }
    pairs: list[Pair] = []
    for family in sorted(families.values(), key=lambda f: -len(f.keys)):
        reader = readers.get(family.stem)
        if family.verb != "set" or reader is None or not arity_consistent(family, WRITER_ARITY):
            continue
        pairs.append(Pair(family, reader, family.keys & reader.keys))
    return pairs


## @brief Whether a candidate pair carries enough evidence to be worth measuring.
## @param pair The candidate pair.
## @return True when it clears both the shared-key and call-site floors.
## @version 1
## @req REQ-DDB-CONFIG-001
def above_threshold(pair: Pair) -> bool:
    """@brief Apply the shared-key and call-site evidence floors to one pair."""
    sites = len(pair.writer.sites) + len(pair.reader.sites)
    return len(pair.shared_keys) >= MIN_SHARED_KEYS and sites >= MIN_PAIR_SITES


## @brief Pair arity-consistent writer families with their reader counterparts.
## @param families Every harvested family, by prefix.
## @return Pairs that passed the arity, shared-key and call-site gates.
## @version 2
## @req REQ-DDB-CONFIG-001
def pair_families(families: dict[str, Family]) -> list[Pair]:
    """@brief Match writer families to readers, keeping only well-evidenced pairs."""
    return [pair for pair in candidate_pairs(families) if above_threshold(pair)]


## @brief The active NamePrefixPattern whose prefix already covers a family.
## @param prefix The family's prefix.
## @param active Prefixes of the currently-active name-prefix patterns.
## @return The covering prefix, or "" when none covers it.
## @version 2
## @req REQ-DDB-CONFIG-001
def covering_prefix(prefix: str, active: Sequence[str]) -> str:
    """CASE-SENSITIVE, matching `shared_key_edges._match_accessor`'s runtime
    `name.startswith(...)`. The build-time diagnostic lowercases both sides,
    which would wrongly report `STORE_SET_` as already covered by the
    built-in `DataModel_Set_` default.

    @brief Find the active pattern covering a family, if any.
    @version 1
    """
    return next((cover for cover in active if cover and prefix.startswith(cover)), "")
