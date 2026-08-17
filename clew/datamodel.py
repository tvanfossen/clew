# SPDX-License-Identifier: MIT
"""TIER 4: a generated data model's OWN manifests, read as the key catalog they are.

WHAT THIS IS NOT. `shared_key_edges`' `--data-model` manifest is a hand-written OWNERSHIP
declaration (`[[keys]] name / writers / readers`) that produces EDGES. This module reads a
different document entirely: the manifest set a code GENERATOR consumes, which names every
key, its class, its namespace, its type and its default, and names no function at all. So it
produces no edges — measured, and stated plainly because the opposite would be the natural
assumption for a module in this neighbourhood.

WHY IT IS WORTH READING ANYWAY. `NamePrefixPattern`'s key is the ENTIRE remainder after
`DataModel_Set_`, one opaque `NS_CLASS_KEY` token, so `Set_X`/`Get_X` already pair correctly
and there is no boundary a manifest could fix. What the index cannot answer without the
manifests is anything about key IDENTITY — "which keys belong to class C", "which namespace
is this", "what type is it", "what is its default" — because `key_name` is that mashed
string and nothing decomposes it. Three gains, none of them an edge count:

  a) key identity structure: namespace / class / key, and the enum a key ranges over;
  b) per-key type and default metadata, which no column in the index carried;
  c) a DECLARED-vs-OBSERVED diagnostic — how much of the declared model the code touches.

THE COMPOSITION RULE IS MEASURED, NOT ASSUMED, and getting it wrong is silent. The generated
accessor is `DataModel_<Set|Get>_<NS>_<CLASS>_<KEY>` with the segments uppercased. The
trap is the separator: an obvious reading strips every non-alphanumeric character, which
scored 104 of 135 against one target's own key list. UNDERSCORES ALREADY IN A SEGMENT ARE
PRESERVED — only characters that cannot appear in a C identifier (a space, in the YAML
dialect) are dropped. With that correction the same target scored 135 of 135.

That cross-check is the load-bearing verification and it is worth naming as a technique: the
manifests and the repo's own key list are two independent statements of the same names,
written by different mechanisms, so agreement between them tests the composition rule in a
way no unit fixture can. A fixture would agree with whatever rule the fixture's author held.

FAIL CLOSED ON SELECTION, because a generator SHIPS EXAMPLE MANIFESTS. A shape-matching
document is not evidence that a repository's data model includes it — a vendored generator's
`examples/` parse identically. What separates them is that the repository's own key list
names the repository's keys and names none of the examples'. So a manifest is admitted only
when at least one of its composed names appears in some discovered key list, and a target
that ships manifests with no key list at all contributes NOTHING and says so by count. A
path or filename rule would be the convenient alternative and is refused: `examples/` is a
convention, and this project has already recorded that a directory NAME is not a boundary.

TWO DIALECTS, TWO PARSERS, ONE ROW TYPE — and no shared field-name mapping, deliberately.
`parse_ingot_manifest` and `parse_udm_manifest` each declare their OWN field mapping in their
own code and both emit `DeclaredKey`. The two dialects share no field name below the top
level and their key tables sit at different nesting depths, so a unified mapping table would
have to GUESS which spelling it was looking at — the heuristic-wearing-a-manifest's-clothes
case this project forbids. The dialect is detected from DOCUMENT SHAPE and RECORDED on every
row, so a consumer never has to infer which generator wrote a key.

WHAT THE UDM DIALECT DECLARES AND THIS INDEX DOES NOT RESOLVE, said out loud rather than left
as an empty column. A UDM key's default is not one value: it is a base `default` plus up to
six per-variant siblings under `type.default_value`, and a build selects among them by a
variant this index does not know. Storing the base and dropping the variants would make a
variant build's real default silently disagree with the index, and choosing among seven is a
heuristic. Its `enum_set` has the same shape one field over — a mapping of variant to an
INLINED member map, with no enum NAME anywhere in it, so there is nothing an `enum_name`
column could honestly hold. So a UDM key carries NO default and NO enum name, and
`unresolved_fields` NAMES the manifest fields that were declared and not resolved. That
distinction is the whole point: without it, "the manifest declares no default" and "the
manifest declares seven defaults and this index resolves none of them" would both be an empty
field, which is the failure mode this module exists to avoid one layer up.

A KEY LIST'S ROLE CANNOT BE READ FROM ITS SHAPE, and that is reported rather than guessed.
The generator's include list, deny list and persistent-key list are ALL flat sequences of the
same uppercase tokens; nothing in any of them says which is which, and only the build
invocation distinguishes them. This module therefore never claims a key is generated or
suppressed. It records `listed` — the key appears in SOME discovered list — which is true
evidence that the key belongs to this repository's model under every reading of every list,
and is exactly what the manifest-set selection needs. `list_count` rides along so an
operator can see when more than one list was found.

@brief Read a generated data model's manifest set as a declared key catalog.
@version 2
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from ._common import logger
from .external import external_roots
from .tomlcompat import toml_module
from .treescan import rel_key
from .vocabulary import DATA_MODEL_DIALECT, bool_check, check

## One of the two dialects this module reads. Its manifest is TOML shaped `[meta] id` /
## `[[classes]] id` / `[[classes.keys]] id`, with a key's type and default as flat scalars.
DIALECT_INGOT = "ingot"

## The other dialect this module reads. Its manifest is YAML shaped `namespace` /
## `classes[].name` / `classes[].data[].name`, with the type one level down at `type.mem`.
## It shares NO field name with the ingot shape below the top level, which is why each
## dialect's field mapping lives in its own parser — see the module docstring.
##
## ITS INT `id` IS NOT AN IDENTITY. 4 of 233 classes and 14 of 1,606 keys in the measured
## corpus carry one, so a reader keying off it would key off a field 99% of the corpus omits.
## The NAME is the identity, and the name is what the generated accessor is composed from.
DIALECT_UDM = "udm"

## The UDM fields this module reads a key's PRESENCE of and never a value from, recorded per
## row in `unresolved_fields`. `type.default_value` is a base plus up to six per-variant
## siblings and `enum_set` is a variant-to-inlined-member-map with no name in it; both are
## DECLARED, and neither is resolvable without knowing the variant a build selects.
_UDM_UNRESOLVED_DEFAULT = "default_value"
_UDM_UNRESOLVED_ENUM = "enum_set"

## Characters dropped from a segment before uppercasing: everything a C identifier cannot
## carry. UNDERSCORES ARE DELIBERATELY ABSENT from this class — see the module docstring; a
## rule that stripped them scored 104 of 135 against a real target's own key list.
_DROPPED_FROM_SEGMENT = re.compile(r"[^0-9A-Za-z_]+")

## What a key-list entry looks like: the generated define name, uppercase and underscored.
## Used to RECOGNISE a flat key list, so the pattern has to reject an ordinary YAML list of
## words without rejecting a real key name.
_LIST_ENTRY = re.compile(r"^[A-Z][A-Z0-9_]*$")

## Directory names never descended into. Dot directories only: a NAME-based exclusion of
## anything else would be the path rule this module refuses to use for selection, and nested
## git trees are excluded separately by the tree they own rather than by what they are called.
_SKIP_PREFIX = "."

## The largest document this module will PARSE, in bytes. A structural bound, decided from
## `stat()` before a byte is read, and it exists because recognising a document by shape means
## parsing documents nobody declared.
##
## MEASURED CAUSE, not a precaution. One control target vendors a YAML parser's BENCHMARK
## CORPUS under its build tree — `style_maps_blck_outer1000_inner1000.yml` is 10.7 MB of
## deliberately pathological nesting — and PyYAML's pure-Python loader does not finish it in
## any time worth waiting for. The build sat in this stage for over twenty-five minutes at
## full CPU. A ceiling cannot be defeated by content, where a timeout or a nesting-depth guard
## both depend on getting partway in.
##
## 2 MiB is ~20x the largest real manifest measured (a 1,606-key model manifest is ~100 KB) and
## ~500x the largest real key list (135 entries, ~4 KB), so no plausible declaration is near
## it. Documents over the ceiling are COUNTED and reported, never silently dropped.
_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


## @brief One key a generator's manifest declares, flattened.
## @version 2
@dataclass(frozen=True)
class DeclaredKey:
    """ONE ROW TYPE FOR BOTH DIALECTS, which is what makes them comparable at all — the two
    parsers disagree about every field name and agree about what a key IS.

    `define_name` is DERIVED and stored anyway, because it is the join key against
    `shared_key_edges.key_name` and re-deriving it at each consumer is how two spellings of
    one rule come to disagree. `manifest` is REPO-RELATIVE without exception: anything
    reachable over MCP is published, and stamping an absolute path here would reintroduce
    the machine-layout disclosure that forced an earlier build-version bump.

    `unresolved_fields` NAMES what the manifest declared and this index did not resolve, and
    it exists so that a NULL is never ambiguous: a NULL `default_value` with an empty
    `unresolved_fields` means the manifest declared no default, and the same NULL with
    `default_value` NAMED means the manifest declared several and the index refused to pick.
    An empty field that means two different things is the defect; this is the distinction.

    @brief One declared data-model key.
    @version 2
    """

    define_name: str
    namespace: str
    class_name: str
    key_id: str
    value_type: str | None
    default_value: str | None
    enum_name: str | None
    helpers: bool | None
    dialect: str
    manifest: str
    unresolved_fields: tuple[str, ...] = ()


## @brief One target's discovered manifest set, with what was declined and why.
## @version 2
@dataclass(frozen=True)
class ManifestSet:
    """A MEASUREMENT of one repository's declared data model, including its zeros.

    Every field defaults to the empty case, so a target with no data model produces a valid
    record rather than an absent one — a correct negative, never an error. The declined
    counts are the point: `manifests_unlisted` says how many shape-matching documents were
    found and refused for want of a key list, which is the difference between "this
    repository has no data model" and "this repository has one and nothing selects it".

    THERE IS NO recognised-but-unread COUNTER any more, and it was REMOVED rather than left at
    zero. It existed because one of the two known dialects was recognised and not parsed; both
    are parsed now, so a counter no code path can increment would be a published zero that
    reads as a measurement. An unrecognised document is declined by shape like any other.

    @brief A discovered data-model manifest set.
    @version 2
    """

    keys: tuple[DeclaredKey, ...] = ()
    manifests: tuple[str, ...] = ()
    listed: frozenset[str] = frozenset()
    list_count: int = 0
    manifests_unlisted: int = 0
    unparsed: int = 0
    ## Candidates refused unread for exceeding `_MAX_DOCUMENT_BYTES`. Reported for the reason
    ## every other refusal here is: a document that was never opened must not be
    ## indistinguishable from one that was opened and declined.
    oversized: int = 0
    ## No TOML parser is importable, so the INGOT half could not be read and an ingot key count
    ## of zero means "could not look" rather than "looked and found none". Recorded because
    ## those are the two readings this project has confused three times, and a count of zero
    ## cannot tell them apart. It says nothing about the UDM half, which is YAML.
    toml_unavailable: bool = False

    ## @brief The dialects that contributed rows, in a stable order.
    ## @return Sorted distinct dialect names.
    ## @version 1
    ## @req REQ-DDB-CONFIG-007
    def dialects(self) -> tuple[str, ...]:
        """DERIVED from the rows rather than stored, so it cannot disagree with them. Two
        dialects in one repository is a real state — an app can pull one generator's model in
        while migrating off another's — so this is a tuple and not a single value.

        @brief The dialects present in this manifest set.
        @return Sorted dialect names.
        @version 1
        """
        return tuple(sorted({key.dialect for key in self.keys}))

    ## @brief Flatten to `build_meta` rows for this build.
    ## @return Mapping of unprefixed data_model keys to string values.
    ## @version 2
    ## @req REQ-DDB-CONFIG-007
    def as_meta(self) -> dict[str, str]:
        """COUNTS ARE STRINGS, non-negotiably: `write_build_signature` drops falsy values, so
        an int `0` vanishes and `"0"` survives. The whole point of this section is that a
        measured zero is recorded, and passing an int would reproduce the silent zero one
        layer down — in the persistence rather than in the detector.

        `keys_by_dialect` exists because `dialect` alone stops being informative the moment
        two dialects appear: a reader would see both names and one total, and could not tell a
        repository with 1,600 keys from one generator and 100 from another from the reverse.

        `unresolved_note` is emitted ONLY when some dialect present actually declares fields
        this index does not resolve, and it is prose on purpose — a consumer reading a NULL
        `default_value` needs to be told that the NULL is BY DIALECT rather than by absence,
        and a count cannot say that. Falsy when nothing is unresolved, so it disappears from
        the payload rather than asserting a policy that did not apply.

        @brief This manifest set as build_meta values.
        @return Unprefixed key to string value.
        @version 2
        """
        per_dialect = {
            dialect: sum(1 for k in self.keys if k.dialect == dialect)
            for dialect in self.dialects()
        }
        return {
            "dialect": "+".join(self.dialects()),
            "keys_by_dialect": ",".join(f"{d}={n}" for d, n in per_dialect.items()),
            "manifests": str(len(self.manifests)),
            "classes": str(len({(k.namespace, k.class_name) for k in self.keys})),
            "keys": str(len(self.keys)),
            "keys_listed": str(sum(1 for k in self.keys if k.define_name in self.listed)),
            "keys_with_unresolved_fields": str(sum(1 for k in self.keys if k.unresolved_fields)),
            "key_lists": str(self.list_count),
            "manifests_unlisted": str(self.manifests_unlisted),
            "manifests_unparsed": str(self.unparsed),
            "documents_oversized": str(self.oversized),
            "toml_unavailable": str(int(self.toml_unavailable)),
            "unresolved_note": self._unresolved_note(),
        }

    ## @brief Prose naming what a present dialect declares and this index does not resolve.
    ## @return The note, or "" when every declared field was resolved.
    ## @version 2
    ## @dg_internal
    def _unresolved_note(self) -> str:
        """SAY IT IN THE PAYLOAD, because the alternative is a consumer reading a NULL and
        concluding the manifest was silent. The note is generated from the rows — it appears
        only if some row actually carries an unresolved field — so it cannot describe a policy
        that did not apply to this repository.

        IT NAMES THE DIALECTS THAT ACTUALLY LEFT SOMETHING UNRESOLVED, not every dialect
        present. On a repository carrying both, `self.dialects()` would put "ingot" into a
        sentence about per-variant defaults ingot does not have — a payload that reads as
        authoritative and is wrong about half its subject.

        @brief The unresolved-fields note for this manifest set.
        @return Prose, or the empty string.
        @version 2
        """
        named = sorted({field for key in self.keys for field in key.unresolved_fields})
        owners = sorted({key.dialect for key in self.keys if key.unresolved_fields})
        if not named:
            return ""
        return (
            f"{'+'.join(owners)} declares per-variant "
            f"{' and '.join(named)} for a key — a base value plus per-variant siblings that a "
            "build selects among by a variant this index does not know — so those columns are "
            "NULL BY DIALECT, not by absence. data_model_keys.unresolved_fields names, per "
            "key, which fields the manifest declared and this index did not resolve; an empty "
            "unresolved_fields beside a NULL means the manifest declared nothing there."
        )


## @brief Compose one manifest triple into the generated accessor's key spelling.
## @param namespace The manifest's namespace.
## @param class_name The class the key sits in.
## @param key_id The key as the manifest writes it.
## @return The uppercase `NS_CLASS_KEY` token the generator emits.
## @version 1
## @req REQ-DDB-SCHEMA-013
def define_name(namespace: str, class_name: str, key_id: str) -> str:
    """THE ONE PLACE the composition rule is spelled, and the rule is measured. See the
    module docstring: underscores inside a segment are preserved and only characters a C
    identifier cannot carry are dropped, which is the difference between 104 and 135 of 135
    against a real target's own key list.

    @brief Compose a define name from a manifest triple.
    @return The composed key spelling.
    @version 1
    """
    parts = (namespace, class_name, key_id)
    return "_".join(_DROPPED_FROM_SEGMENT.sub("", str(part)).upper() for part in parts)


## @brief Read a candidate document's text, or refuse it for being too large.
## @param path The candidate document.
## @return Its text, or None when it exceeds the ceiling or cannot be decoded.
## @version 1
## @dg_internal
def _small_text(path: Path) -> str | None:
    """SIZE FIRST, from `stat()`, before a byte is read. Reading and then measuring would
    already have paid the cost the ceiling exists to avoid, and on the measured case that cost
    is unbounded rather than merely large.

    @brief Read a document only if it is small enough to be a declaration.
    @return The text, or None.
    @version 1
    """
    try:
        if path.stat().st_size > _MAX_DOCUMENT_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


## @brief Count candidates that exceed the parse ceiling.
## @param paths Candidate documents.
## @return How many are larger than `_MAX_DOCUMENT_BYTES`.
## @version 1
## @dg_internal
def _oversized_count(paths: Iterable[Path]) -> int:
    """@brief Count documents refused unread for their size.

    @version 1
    """
    total = 0
    for path in paths:
        try:
            total += int(path.stat().st_size > _MAX_DOCUMENT_BYTES)
        except OSError:
            continue
    return total


## @brief Render a manifest scalar for storage, preserving how it was written.
## @param value The default as the manifest declares it.
## @return A string, or None when the manifest omitted the field.
## @version 1
## @dg_internal
def _scalar(value: object) -> str | None:
    """TOML distinguishes `false` from `0` and this keeps that distinction, because a boolean
    default and a zero default are different facts about a key and `str(False)` is not
    `"0"`. None stays None so an omitted field reads as SQL NULL rather than as the string
    "None", which would be a value that looks declared and is not.

    @brief Stringify a declared default without flattening its type.
    @version 1
    """
    return None if value is None else str(value)


## @brief Parse one document as an ingot data-model manifest.
## @param path The candidate TOML document.
## @param repo_root Root the stored manifest path is made relative to.
## @return The keys it declares, or None when the document is not one of these manifests.
## @version 2
## @req REQ-DDB-SCHEMA-013
def parse_ingot_manifest(path: Path, repo_root: Path) -> tuple[DeclaredKey, ...] | None:
    """SHAPE-GATED, and the gate is the whole discriminator: a document qualifies only when
    it carries a `classes` list whose entries carry both an `id` and a `keys` list. Ordinary
    project TOML — a lint config, a tool manifest — has no such shape, so nothing needs to
    know a filename.

    Returns None for "not this kind of document" and `()` for "one of these and it declares
    nothing", which are different answers: the first must not count against the target and
    the second is a manifest that contributed no rows. Collapsing them would make an empty
    manifest look like a lint file.

    THE TOLERANT TOML LOADER, not the strict one, and the difference matters here. This is a
    DISCOVERY path over every TOML document in a repository, reached whether or not anyone
    declared a data model — so on the declared 3.10 floor without the backport installed, the
    strict loader would fail the build of every target, including the overwhelming majority
    that have no data model at all. `discover` reports the absence instead (`toml_unavailable`).
    The strict loader is right where an owner DECLARED a manifest and it cannot be read; that
    is a different situation and it has a different caller.

    @brief Parse an ingot manifest, or decline the document.
    @return Declared keys, or None when the shape does not match.
    @version 2
    """
    toml = toml_module()
    text = _small_text(path) if toml is not None else None
    if toml is None or text is None:
        return None
    try:
        doc = toml.loads(text)
    except toml.TOMLDecodeError:
        return None
    classes = doc.get("classes")
    if not isinstance(classes, list) or not _is_ingot_class_list(classes):
        return None
    namespace = str(doc.get("meta", {}).get("id", "")) if isinstance(doc.get("meta"), dict) else ""
    manifest = rel_key(path, repo_root)
    return tuple(_ingot_keys(classes, namespace, manifest))


## @brief True when a `classes` list has the ingot manifest's shape.
## @param classes The parsed `classes` value.
## @return True when at least one entry carries both an `id` and a `keys` list.
## @version 1
## @dg_internal
def _is_ingot_class_list(classes: list) -> bool:
    """@brief Recognise the ingot class-list shape.

    @version 1
    """
    return any(
        isinstance(entry, dict) and "id" in entry and isinstance(entry.get("keys"), list)
        for entry in classes
    )


## @brief Flatten an ingot class list into declared keys.
## @param classes The manifest's `classes` list.
## @param namespace The manifest's namespace.
## @param manifest Repo-relative manifest path.
## @return One DeclaredKey per `[[classes.keys]]` table carrying an id.
## @version 1
## @dg_internal
def _ingot_keys(classes: list, namespace: str, manifest: str) -> Iterable[DeclaredKey]:
    """A key with no `id` is SKIPPED rather than stored under an empty name: its define name
    would collide with every other id-less key in the same class, merging unrelated keys into
    one row that looks like a real one.

    @brief Yield the keys an ingot class list declares.
    @version 1
    """
    for entry in classes:
        if not isinstance(entry, dict):
            continue
        class_name = str(entry.get("id", ""))
        for key in entry.get("keys") or []:
            key_id = str(key.get("id", "")) if isinstance(key, dict) else ""
            if not key_id:
                continue
            yield DeclaredKey(
                define_name=define_name(namespace, class_name, key_id),
                namespace=namespace,
                class_name=class_name,
                key_id=key_id,
                value_type=_scalar(key.get("type")),
                default_value=_scalar(key.get("default")),
                enum_name=_scalar(key.get("enum")),
                helpers=None if key.get("helpers") is None else bool(key.get("helpers")),
                dialect=DIALECT_INGOT,
                manifest=manifest,
            )


## @brief Load a YAML document only when it has the UDM manifest shape.
## @param path The candidate YAML document.
## @return The parsed mapping, or None when the document is not one of these manifests.
## @version 1
## @dg_internal
def _udm_document(path: Path) -> dict | None:
    """ONE shape gate for this dialect, in one place, because the alternative is a recogniser
    and a parser that can drift apart — and the drift would be silent in the direction that
    matters: a recogniser slightly looser than its parser reports manifests it then reads no
    keys from, which looks exactly like a manifest that declares nothing.

    `namespace` plus a `classes` list whose entries carry a `data` list is this dialect's
    shape, and it shares no field name with the ingot shape.

    @brief Parse a UDM manifest document, or decline it.
    @return The document, or None.
    @version 1
    """
    import yaml

    text = _small_text(path)
    if text is None:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(doc, dict) or "namespace" not in doc:
        return None
    classes = doc.get("classes")
    ok = isinstance(classes, list) and any(
        isinstance(entry, dict) and isinstance(entry.get("data"), list) for entry in classes
    )
    return doc if ok else None


## @brief Parse one document as a UDM data-model manifest.
## @param path The candidate YAML document.
## @param repo_root Root the stored manifest path is made relative to.
## @return The keys it declares, or None when the document is not one of these manifests.
## @version 1
## @req REQ-DDB-SCHEMA-013
def parse_udm_manifest(path: Path, repo_root: Path) -> tuple[DeclaredKey, ...] | None:
    """A SECOND PARSER, not a second branch of the first, and the field mapping below is the
    argument for it: `namespace` / `name` / `name` / `type.mem` shares not one spelling with
    ingot's `meta.id` / `id` / `id` / `type`, and the key table sits a level deeper. A unified
    mapping would have to guess which dialect it was reading; the shape gate decides once and
    each parser then knows exactly what it is looking at.

    Returns None for "not this kind of document" and `()` for "one of these and it declares
    nothing", the same two distinct answers `parse_ingot_manifest` returns and for the same
    reason.

    @brief Parse a UDM manifest, or decline the document.
    @return Declared keys, or None when the shape does not match.
    @version 1
    """
    doc = _udm_document(path)
    if doc is None:
        return None
    namespace = str(doc.get("namespace", ""))
    return tuple(_udm_keys(doc["classes"], namespace, rel_key(path, repo_root)))


## @brief Flatten a UDM class list into declared keys.
## @param classes The manifest's `classes` list.
## @param namespace The manifest's namespace.
## @param manifest Repo-relative manifest path.
## @return One DeclaredKey per `classes[].data[]` entry carrying a name.
## @version 1
## @dg_internal
def _udm_keys(classes: list, namespace: str, manifest: str) -> Iterable[DeclaredKey]:
    """THE NAME IS THE IDENTITY, never the optional int `id`: 4 of 233 classes and 14 of 1,606
    keys in the measured corpus carry one, so keying off it would key off a field the corpus
    almost entirely omits — and the generated accessor is composed from the name regardless.
    A key with no name is skipped for the reason `_ingot_keys` skips an id-less key.

    NO DEFAULT AND NO ENUM NAME ARE STORED, and their absence is RECORDED instead. This
    dialect's default is a base plus up to six per-variant siblings and its `enum_set` is a
    variant-to-inlined-member-map with no name in it, so there is no single value either column
    could hold that a variant build would agree with. Storing the base and dropping the
    variants is the tempting version and it is the wrong one: the index would then disagree
    with a real build silently, where an unresolved field disagrees with nothing.

    @brief Yield the keys a UDM class list declares.
    @version 1
    """
    for entry in classes:
        if not isinstance(entry, dict):
            continue
        class_name = str(entry.get("name", ""))
        for key in entry.get("data") or []:
            if not isinstance(key, dict):
                continue
            key_id = str(key.get("name", ""))
            if not key_id:
                continue
            type_block = key.get("type") if isinstance(key.get("type"), dict) else {}
            helpers = key.get("generate_helpers")
            yield DeclaredKey(
                define_name=define_name(namespace, class_name, key_id),
                namespace=namespace,
                class_name=class_name,
                key_id=key_id,
                value_type=_scalar(type_block.get("mem")),
                default_value=None,
                enum_name=None,
                helpers=None if helpers is None else bool(helpers),
                dialect=DIALECT_UDM,
                manifest=manifest,
                unresolved_fields=_udm_unresolved(key, type_block),
            )


## @brief Name the fields this key declares and this index does not resolve.
## @param key The manifest's key mapping.
## @param type_block The key's `type` mapping, empty when it has none.
## @return The unresolved field names, in a stable order.
## @version 1
## @dg_internal
def _udm_unresolved(key: dict, type_block: dict) -> tuple[str, ...]:
    """PRESENCE, not value — that is the whole contract. A key that declares no default at all
    (280 of 1,606 in the measured corpus) gets an EMPTY tuple, and a key that declares one or
    seven gets the field named. Those two states are what a bare NULL cannot tell apart, and
    conflating them is the failure this module's docstring opens on.

    @brief The declared-but-unresolved field names for one key.
    @return Field names, empty when everything declared was resolved.
    @version 1
    """
    named: list[str] = []
    if type_block.get(_UDM_UNRESOLVED_DEFAULT) is not None:
        named.append(_UDM_UNRESOLVED_DEFAULT)
    if key.get(_UDM_UNRESOLVED_ENUM) is not None:
        named.append(_UDM_UNRESOLVED_ENUM)
    return tuple(named)


## @brief Read a flat key list, if the document is one.
## @param path The candidate YAML document.
## @return The define names it lists, or None when the document is not a flat key list.
## @version 1
## @req REQ-DDB-SCHEMA-013
def read_key_list(path: Path) -> frozenset[str] | None:
    """RECOGNISED BY SHAPE, and the shape has to be tight enough that an ordinary YAML
    sequence does not qualify. Every entry must be a define-name token — uppercase, digits
    and underscores, starting with a letter — and the list must be non-empty, so a
    sequence of file paths, of lowercase words or of mappings is declined.

    This function does NOT decide what the list MEANS. Include, deny and persistent-key
    lists are the same shape and only the build invocation tells them apart; see the module
    docstring on why `listed` is the honest column.

    @brief Read a flat define-name list, or decline the document.
    @return The listed names, or None.
    @version 1
    """
    import yaml

    text = _small_text(path)
    if text is None:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(doc, list) or not doc:
        return None
    if not all(isinstance(item, str) and _LIST_ENTRY.match(item) for item in doc):
        return None
    return frozenset(doc)


## @brief Every candidate document under a repo, excluding dot trees and nested git trees.
## @param repo_root The repository root.
## @param excludes Subtrees the BUILD excluded, pruned during the descent.
## @return (TOML candidates, YAML candidates), both sorted for a stable build.
## @version 3
## @dg_internal
def _candidates(repo_root: Path, excludes: tuple[Path, ...] = ()) -> tuple[list[Path], list[Path]]:
    """NESTED GIT TREES ARE EXCLUDED BY THEIR TREE, not by their name. A vendored generator
    is somebody else's repository and its example manifests are its own; `external_roots`
    already answers "which subtrees belong to someone else" and reusing it means this module
    does not grow a second, weaker answer. A copied-in directory with no git tree of its own
    is FIRST PARTY and stays a candidate — the repository committed it and owns it — and if
    it holds examples, the key-list gate is what declines them.

    PRUNED DURING THE DESCENT, never filtered afterwards, and this is not a micro-optimisation
    — the first version used `rglob("*")` and tested each result, which did not finish a walk
    of one control target in FIVE MINUTES. `treescan._files_under` already documents exactly
    why: `.git`, `.venv` and build output get walked in full only to be dropped, and this
    module already imported that module while repeating the mistake it warns about. Pruning
    makes the walk sized by what survives.

    `followlinks=False` matches the recursive-glob behaviour and is load-bearing here for the
    same reason: a symlink pointing at an ancestor is a cycle, and a walk that follows one
    never terminates at all.

    THE BUILD'S OWN EXCLUDES ARE HONOURED, and that is a correctness requirement rather than a
    speed one. A generated data model's OUTPUT lands in a build directory, and this layer's
    whole premise is that it reads the generator's SOURCES and never its output — an index that
    is a function of whether somebody ran a build would make two indexes of one commit disagree
    about which keys exist. Excluding what the build excluded means the catalog cannot see a
    generated artifact even by accident. The list arrives from the same `extra_exclude` doxygen
    received, so the stage looks exactly where the index looks and nothing re-derives a scope
    that could differ.

    @brief Collect candidate manifest and key-list documents.
    @return TOML and YAML candidate paths.
    @version 3
    """
    foreign = {(repo_root / root) for root in external_roots(repo_root)}
    foreign |= set(excludes)
    toml_paths: list[Path] = []
    yaml_paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(_SKIP_PREFIX) and (here / name) not in foreign
        )
        for name in sorted(filenames):
            suffix = Path(name).suffix.lower()
            if suffix == ".toml":
                toml_paths.append(here / name)
            elif suffix in (".yaml", ".yml"):
                yaml_paths.append(here / name)
    return toml_paths, yaml_paths


## @brief Discover a repository's declared data-model manifest set.
## @param repo_root The repository root, or None when the build has none.
## @param excludes Subtrees the BUILD excluded, so this layer looks where the index looks.
## @return The manifest set, empty when the repository declares no data model.
## @version 2
## @req REQ-DDB-SCHEMA-013
def discover(repo_root: Path | None, excludes: tuple[Path, ...] = ()) -> ManifestSet:
    """TWO PASSES, and the ORDER is the fail-closed rule: every key list is collected first,
    and only then is a manifest admitted — on the evidence that the repository's own list
    names at least one of its keys. A one-pass version that took every shape-matching
    document would index a vendored generator's examples as though they were the
    repository's model, and would report a plausible count while doing it.

    A target with no data model returns the empty set. That is a CORRECT NEGATIVE and never
    an error: most repositories have no generated data model, and raising here would make
    the stage a gate on a feature nobody asked for.

    A MISSING TOML PARSER NO LONGER STOPS THE WHOLE PASS, and that changed when the second
    dialect became readable. The ingot dialect is TOML and the UDM dialect is YAML, so an
    interpreter with no `tomllib` and no `tomli` backport can still read a UDM model in full —
    returning early here would have reported "could not look" about a half that was perfectly
    readable. `toml_unavailable` narrows to exactly what it can still honestly claim: the
    INGOT half could not be looked at.

    @brief Discover and select a repository's data-model manifest set.
    @return The discovered manifest set.
    @version 3
    """
    if repo_root is None:
        return ManifestSet()
    no_toml = toml_module() is None
    if no_toml:
        logger.warning(
            "data_model: no TOML parser is importable, so no INGOT manifest could be READ — a "
            "zero ingot key count means 'could not look', not 'looked and found none'. The "
            "UDM dialect is YAML and was still read. Install the tomli backport to read both.",
        )
    toml_paths, yaml_paths = _candidates(repo_root, excludes)
    listed, list_count, udm_paths = _classify_yaml(yaml_paths)
    found = _select(toml_paths, udm_paths, repo_root, listed, list_count)
    return replace(
        found,
        oversized=_oversized_count([*toml_paths, *yaml_paths]),
        toml_unavailable=no_toml,
    )


## @brief Sort the YAML candidates into key lists and UDM manifests.
## @param yaml_paths Every YAML candidate under the repository.
## @return (every listed define name, how many lists, the UDM manifest paths).
## @version 1
## @dg_internal
def _classify_yaml(yaml_paths: list[Path]) -> tuple[frozenset[str], int, list[Path]]:
    """KEY LIST FIRST, because the two shapes are disjoint at the top level — a flat sequence
    is never a mapping — so the order costs nothing and the cheaper test runs first.

    Only the PATHS of the UDM manifests are returned, not their parsed documents. A repository
    holding thousands of YAML documents would otherwise be asked to hold every one of them in
    memory to select a handful, and re-parsing exactly the documents that passed the shape gate
    is a bounded cost measured in tens of files.

    @brief Split YAML candidates into key lists and UDM manifests.
    @return Listed names, list count, and UDM manifest paths.
    @version 1
    """
    listed: set[str] = set()
    list_count = 0
    udm_paths: list[Path] = []
    for path in yaml_paths:
        names = read_key_list(path)
        if names is not None:
            listed |= names
            list_count += 1
        elif _udm_document(path) is not None:
            udm_paths.append(path)
    return frozenset(listed), list_count, udm_paths


## @brief Parse every candidate that IS a manifest, in either dialect.
## @param toml_paths Candidate TOML documents, read as the ingot dialect.
## @param udm_paths Candidate YAML documents that passed the UDM shape gate.
## @param repo_root Root the stored manifest paths are relative to.
## @return (repo-relative manifest path, its declared keys) per document that parsed.
## @version 1
## @dg_internal
def _parsed_manifests(
    toml_paths: list[Path],
    udm_paths: list[Path],
    repo_root: Path,
) -> Iterable[tuple[str, tuple[DeclaredKey, ...]]]:
    """EACH DIALECT THROUGH ITS OWN PARSER, and the dispatch is the shape gate that already
    ran — a TOML candidate goes to the ingot parser and a document that passed the UDM shape
    gate goes to the UDM parser. Nothing here inspects a field name, so there is no place for a
    unified mapping to creep back in.

    @brief Parse both dialects' manifests into one stream.
    @return Manifest path and keys per parsed document.
    @version 1
    """
    for path in toml_paths:
        ingot = parse_ingot_manifest(path, repo_root)
        if ingot is not None:
            yield rel_key(path, repo_root), ingot
    for path in udm_paths:
        udm = parse_udm_manifest(path, repo_root)
        if udm is not None:
            yield rel_key(path, repo_root), udm


## @brief Admit each parsed manifest whose keys the repository's own lists name.
## @param toml_paths Candidate TOML documents.
## @param udm_paths Candidate YAML documents that passed the UDM shape gate.
## @param repo_root Root the stored manifest paths are relative to.
## @param listed Every define name any discovered key list carries.
## @param list_count How many key lists were discovered.
## @return The selected manifest set.
## @version 2
## @dg_internal
def _select(
    toml_paths: list[Path],
    udm_paths: list[Path],
    repo_root: Path,
    listed: frozenset[str],
    list_count: int,
) -> ManifestSet:
    """The refusals are COUNTED, because the two ways this returns nothing mean opposite
    things. `manifests_unlisted > 0` with `keys == 0` says the repository HAS manifests and
    no list selects them — an operator can act on that. Both counts at zero says there is no
    data model here, which is the ordinary case.

    THE GATE IS DIALECT-BLIND, deliberately: it asks whether the repository's own key lists
    name any of a manifest's composed keys, and that question is answerable identically for
    both dialects because both compose their names through `define_name`. A per-dialect gate
    would be a second place for the selection rule to live.

    @brief Select the manifests the repository's key lists vouch for.
    @return The manifest set.
    @version 2
    """
    keys: list[DeclaredKey] = []
    manifests: list[str] = []
    unlisted = 0
    for manifest, parsed in _parsed_manifests(toml_paths, udm_paths, repo_root):
        if not any(key.define_name in listed for key in parsed):
            unlisted += 1
            continue
        keys.extend(parsed)
        manifests.append(manifest)
    return ManifestSet(
        keys=tuple(keys),
        manifests=tuple(manifests),
        listed=listed,
        list_count=list_count,
        manifests_unlisted=unlisted,
    )


## @brief Create the data_model_keys table if it does not already exist.
## @param conn Open connection to the database being built.
## @return None.
## @version 2
## @req REQ-DDB-SCHEMA-013
def _ensure_table(conn: sqlite3.Connection) -> None:
    """UNIQUE on `(define_name, manifest)` rather than on `define_name` alone, because two
    manifests declaring the same name is a real condition in a repository mid-refactor and
    silently keeping one of them would hide it. Every enumerated column's clause comes from
    `vocabulary`, which is the only place a CHECK literal may live.

    `unresolved_fields` CARRIES NO CHECK, and that is a decision rather than an omission: its
    value is a SET of declared field names, not one of them, so no `IN` clause can express it.
    It is NULL when nothing was unresolved rather than an empty string, so a consumer's test
    for it is the same NULL test every other optional column here takes.

    @brief Idempotent data_model_keys table creation.
    @version 2
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS data_model_keys (
            define_name   TEXT NOT NULL,
            namespace     TEXT NOT NULL,
            class_name    TEXT NOT NULL,
            key_id        TEXT NOT NULL,
            value_type    TEXT,
            default_value TEXT,
            enum_name     TEXT,
            helpers       INTEGER {bool_check("helpers")},
            dialect       TEXT NOT NULL {check("data_model_keys", "dialect")},
            manifest      TEXT NOT NULL,
            unresolved_fields TEXT,
            listed        INTEGER NOT NULL {bool_check("listed")},
            observed      INTEGER NOT NULL {bool_check("observed")},
            UNIQUE(define_name, manifest)
        )
        """,
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_data_model_keys_define ON data_model_keys(define_name)",
    )
    conn.commit()


## @brief The shared-key vocabulary the built index actually observed.
## @param conn Open connection to the database being built.
## @return Distinct `shared_key_edges.key_name` values, empty when the table does not exist.
## @version 1
## @dg_internal
def _observed_keys(conn: sqlite3.Connection) -> frozenset[str]:
    """Tolerates a MISSING TABLE rather than requiring one, because `shared_key_edges` is
    created by whichever of its own two stages runs first and a target with no accessor
    convention legitimately has neither. An exception here would turn "this repository has
    no dataflow" into a build failure.

    @brief Read the observed shared-key vocabulary.
    @return Distinct observed key names.
    @version 1
    """
    try:
        rows = conn.execute("SELECT DISTINCT key_name FROM shared_key_edges").fetchall()
    except sqlite3.OperationalError:
        return frozenset()
    return frozenset(str(row[0]) for row in rows)


## @brief Layer: persist a repository's declared data-model key catalog.
## @param db_path Path to the clew.db being built.
## @param repo_root The repository root, or None.
## @param excludes Subtrees the BUILD excluded, so this layer looks where the index looks.
## @return The manifest set that was discovered, for stamping.
## @version 2
## @req REQ-DDB-SCHEMA-013
def import_data_model_keys(
    db_path: Path, repo_root: Path | None, excludes: tuple[Path, ...] = ()
) -> ManifestSet:
    """RUNS AFTER the shared-key stages, because `observed` is a join against the vocabulary
    they wrote. That ordering is load-bearing and not incidental: run above them and every
    row would read `observed = 0`, which is a plausible answer — the declared-vs-observed
    diagnostic would report a repository touching none of its own data model.

    THE TABLE IS CREATED EVEN WHEN THERE ARE NO ROWS, so an empty answer is distinguishable
    from a table that was never built. A consumer querying a target with no data model gets
    zero rows from a real table, which is a measurement; a missing table is not — it cannot
    be told from an index built before this layer existed.

    @brief Import the declared data-model key catalog.
    @return The discovered manifest set.
    @version 2
    """
    found = discover(repo_root, excludes)
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_table(conn)
        observed = _observed_keys(conn)
        conn.executemany(
            """
            INSERT OR IGNORE INTO data_model_keys
                (define_name, namespace, class_name, key_id, value_type, default_value,
                 enum_name, helpers, dialect, manifest, unresolved_fields, listed, observed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    key.define_name,
                    key.namespace,
                    key.class_name,
                    key.key_id,
                    key.value_type,
                    key.default_value,
                    key.enum_name,
                    None if key.helpers is None else int(key.helpers),
                    key.dialect,
                    key.manifest,
                    ",".join(key.unresolved_fields) or None,
                    int(key.define_name in found.listed),
                    int(key.define_name in observed),
                )
                for key in found.keys
            ],
        )
        conn.commit()
    finally:
        conn.close()
    _log(found, observed)
    return found


## @brief Report what the data-model pass found, including its zeros.
## @param found The discovered manifest set.
## @param observed The observed shared-key vocabulary.
## @return None.
## @version 1
## @dg_internal
def _log(found: ManifestSet, observed: frozenset[str]) -> None:
    """The UNSELECTED count is logged at WARNING, because it is the one state an operator can
    act on: manifests exist and no key list vouches for them, so the catalog is empty for a
    reason that is not "there is no data model here".

    LISTS BUT NO MANIFESTS IS ITS OWN WARNING, and it is the one this layer was measured to
    need. A repository can declare its model in a SHARED SUBMODULE while keeping the key list
    that selects from it in the app — and `_candidates` excludes nested git trees, so the
    manifests and the evidence that vouches for them end up on opposite sides of that boundary.
    Measured on a real target: 37 manifests inside the nested tree, the 2 key lists naming
    their keys outside it, and a catalog of zero keys with `manifests_unlisted` also zero —
    which is byte-identical to a repository that has no data model at all. The counts alone
    cannot separate those two, so the warning says which one this is.

    THE UNRESOLVED-FIELDS NOTE IS LOGGED, not only stored, because a build log is where an
    owner first sees this layer at all. A reader who never queries the table must still learn
    that a UDM key's NULL default is a policy and not an absence.

    @brief Log the data-model pass's measurement.
    @version 2
    """
    if found.list_count and not found.manifests:
        logger.warning(
            "data_model: %d key list(s) naming %d define(s) were found and NO manifest was "
            "selected, which is NOT the same measurement as 'this repository has no data "
            "model'. If the model's manifests live in a NESTED GIT TREE — a shared submodule "
            "— they are excluded by tree and a first-party key list cannot vouch for them.",
            found.list_count,
            len(found.listed),
        )
    if found.manifests_unlisted:
        logger.warning(
            "data_model: %d shape-matching manifest(s) declined — no discovered key list "
            "names any of their keys, so nothing vouches for them being this repository's "
            "model rather than a vendored generator's examples",
            found.manifests_unlisted,
        )
    logger.info(
        "data_model: %d key(s) over %d class(es) from %d manifest(s) in dialect(s) %s; "
        "%d key list(s) found; %d declared key(s) also observed in the shared-key layer "
        "(of %d observed)",
        len(found.keys),
        len({(k.namespace, k.class_name) for k in found.keys}),
        len(found.manifests),
        "+".join(found.dialects()) or "none",
        found.list_count,
        sum(1 for k in found.keys if k.define_name in observed),
        len(observed),
    )
    note = found.as_meta()["unresolved_note"]
    if note:
        logger.info("data_model: %s", note)


## Re-exported so a consumer importing the dialect names does not reach into `vocabulary`.
__all__ = [
    "DATA_MODEL_DIALECT",
    "DIALECT_INGOT",
    "DIALECT_UDM",
    "DeclaredKey",
    "ManifestSet",
    "define_name",
    "discover",
    "import_data_model_keys",
    "parse_ingot_manifest",
    "parse_udm_manifest",
    "read_key_list",
]
