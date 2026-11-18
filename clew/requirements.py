# SPDX-License-Identifier: MIT
"""Requirements traceability: requirements.yaml ingestion + `@req` edges.

Three stages, run after the call-graph layers and before reachability:

  1. `ingest_requirements_yaml` — loads a target repo's OPTIONAL, format-
     tolerant `requirements.yaml`. Ingests only the flat `[{id, ...}]` shape
     (id/name columns via the repo's DECLARED `.clew.yaml` `guard:`
     `impact.requirements` mapping when present, else the {id,title,...}
     convention). Nested/unknown catalogs (e.g. a `domains:` tree) yield 0
     rows — the structure is never guessed. No universal format is assumed.

  2. `import_req_edges` — scans `memberdef.briefdescription` and
     `memberdef.detaileddescription` for `@req <id>` tags, keeping ids that
     match the target repo's DECLARED pattern
     (`.clew.yaml` `guard.validate.tags.req.pattern`) or a permissive
     fallback — NOT a hardcoded `REQ-\\d+`. Populates
     `req_edges(req_id, memberdef_rowid)` regardless of whether the catalog
     parsed. There is NO confidence column: the `[inferred]` marker was retired
     2026-07-30 — a requirement either has an implementer or it does not.
     NOTHING CHECKS that a requirement claiming `implemented` has one: the
     pre-commit coverage audit that did is DELETED and was not replaced.

  3. `import_req_test_edges` — the subset of req_edges rows whose
     memberdef is itself a test function (name convention or file path),
     materialized into `req_test_edges(req_id, test_memberdef_rowid)` so
     lookup_requirement can cheaply separate "implementing functions"
     from "covering tests" without re-deriving the heuristic at query time.

@brief Requirements traceability ingestion (requirements.yaml + @req edges).
@version 2
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from ._common import logger

# Capture the token AFTER `@req` — just the id, nothing else —
# WITHOUT assuming its id format: the id shape is validated
# separately against the target repo's DECLARED pattern (see
# resolve_req_id_pattern). `@req` keyword match is case-insensitive; the
# captured id token preserves case so it can be matched against a
# case-sensitive declared pattern.
#
# `<` TERMINATES the id and satisfies the terminator lookahead, because the text
# being scanned is doxygen's XML-ish description, not the author's source line.
# `@req` is an UNKNOWN command to doxygen, so it is absorbed into whatever
# paragraph command precedes it, and when the tag is the LAST line of a doc block
# the stored text is `@req REQ-X-FOO-001</para>` with no separating space. The
# previous `(\S+?)(?=\s|$)` then captured `REQ-X-FOO-001</para>`, which fails
# every declared pattern, so the edge was dropped in SILENCE — measured on this
# repo's own index: 104 tagged functions produced 20 edges. A requirement id
# cannot contain `<`, so stopping there is a strict improvement.
#
# That same terminator once also mis-graded a trailing `[inferred]` CONFIDENCE
# marker, which this project used to support. The marker was retired 2026-07-30 —
# "they should simply be the stated ID, inferred is noise" — so the group is gone
# and every tag is simply an id. Kept as a note because the terminator fix above
# was found through that second symptom.
_REQ_TAG_TOKEN_RE = re.compile(
    r"@req\s+([^\s<]+?)(?=[\s<]|$)",
    re.IGNORECASE,
)

# Doxygen rewrites an `@req`-aliased xrefitem (ALIASES =
# "req=@xrefitem req_trace ...") into an `<xrefsect>` whose
# `<xrefdescription>` carries the id — the literal `@req` token is GONE from
# the stored description. To keep req_edges populating REGARDLESS of whether a
# repo passes `@req` through literally (demobot) or via an xrefitem alias
# also scan xrefdescription blocks. We do NOT hardcode the xref title
# or key (both are repo-defined in the alias); instead every candidate token
# inside a xrefdescription is validated against the DECLARED req id pattern,
# so only real requirement ids survive.
_XREF_DESC_RE = re.compile(
    r"<xrefdescription>(.*?)</xrefdescription>",
    re.IGNORECASE | re.DOTALL,
)
# A bare id-like token (letters/digits with internal `-`/`_`); each is only
# kept if it fully matches the declared/permissive req id pattern.
_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

# Permissive fallback used when the target repo declares NO `@req` id pattern
# (no `guard:` section in .clew.yaml, or no validate.tags.req.pattern). Deliberately NOT
# the old hardcoded `REQ-\d+` — it accepts any `REQ-<alnum>...` id (demobot's
# `REQ-0621`, `REQ-PROJ-NAV-002`, etc.) so req_edges populate for any
# repo that has not declared a stricter shape.
_PERMISSIVE_REQ_ID_RE = re.compile(r"^REQ-[A-Za-z0-9][A-Za-z0-9_-]*$")


## @brief Load a target repo's gate config: the `guard:` section of its `.clew.yaml`.
## @param repo_root Repo root whose `.clew.yaml` is read.
## @return Parsed config dict, or None if absent / unusable.
## @version 7
## @req REQ-DDB-CONFIG-001
def load_guard_config(repo_root: Path | str) -> dict | None:
    """Single source of the config load so both the `@req` pattern resolution
    and the catalog column mapping read from ONE parsed dict. Returns None
    (not an error) when there is nothing declared — every declaration-driven
    lookup then falls back to its permissive built-in default. An invalid section
    is reported by `guardconfig.read_guard_config` and also returns None.

    @brief Load the target repo's declared gate config.
    """
    from .guardconfig import read_guard_config

    read = read_guard_config(repo_root)
    return read.config if read.usable() else None


## @brief Resolve the target repo's DECLARED `@req` id pattern (or fallback).
## @param guard_cfg Parsed `guard:` section of .clew.yaml, or None.
## @return Compiled regex the captured `@req` id token must fully match.
## @version 3
## @req REQ-DDB-CONFIG-001
def resolve_req_id_pattern(guard_cfg: dict | None) -> re.Pattern[str]:
    """Return the compiled `validate.tags.req.pattern` from the guard config.

    When no config or no declared pattern is present, fall back to the
    PERMISSIVE default — never to a hardcoded per-repo format.

    @brief Resolve the declared @req id pattern (permissive fallback).
    @version 3
    """
    if guard_cfg:
        from .guard import config as dg_config

        validate = dg_config.get_validate(guard_cfg)
        declared = (validate.get("tags", {}).get("req", {}) or {}).get("pattern")
        if declared:
            logger.info("requirements: using declared @req id pattern %r", declared)
            return re.compile(declared)
    return _PERMISSIVE_REQ_ID_RE


## @brief Resolve the DECLARED requirements-catalog id/name column names.
## @param guard_cfg Parsed `guard:` section of .clew.yaml, or None.
## @return (id_column, name_column) — declared mapping or the shared {id,name} default.
## v5 (2.0.0): reads the top-level `requirements:` section; the default pair is the gate's.
## @version 5
## @req REQ-DDB-CONFIG-001
def resolve_catalog_columns(guard_cfg: dict | None) -> tuple[str, str]:
    """Return the id/name column keys for a flat requirements catalog.

    Reads `requirements.{id_column,name_column}` (the top-level section, which the gate reads
    too); otherwise the ONE default pair both readers share (R5-CFG F8).

    @brief Resolve declared catalog id/name columns (id/name default).
    @version 5
    """
    from .guard import config as dg_config

    id_col, name_col = (
        dg_config.REQUIREMENTS_ID_COLUMN_DEFAULT,
        dg_config.REQUIREMENTS_NAME_COLUMN_DEFAULT,
    )
    if guard_cfg:
        req = dg_config.get_requirements(guard_cfg)
        id_col = req.get("id_column", id_col)
        name_col = req.get("name_column", name_col)
    return id_col, name_col


## @brief Decide whether YAML data is a flat list of id-bearing req mappings.
## @param data Parsed YAML document.
## @param id_col The id column key to look for.
## @return True only for a non-empty list of dicts carrying an id-like key.
## @version 4
## @req REQ-DDB-CONFIG-003
def _is_flat_req_list(data: object, id_col: str) -> bool:
    """Detect the flat `[{id, ...}, ...]` catalog shape.

    Anything else — a nested `{domains: ...}` catalog, a scalar, an
    empty document — is NOT assumed to be ingestible; the caller ingests 0
    catalog rows rather than guessing at the structure.

    @brief Recognise the flat id-bearing requirements-list shape.
    @version 4
    """
    if not isinstance(data, list) or not data:
        return False
    if not all(isinstance(entry, dict) for entry in data):
        return False
    return any((id_col in entry) or ("id" in entry) for entry in data)


## @brief Create (or reset) the `requirements` table.
## v2 (2.0.0, S4): the 29148 columns and `extra`.
## @version 2
## @dg_internal
def _create_requirements_table(conn: sqlite3.Connection) -> None:
    """Create the requirements table schema, dropping any prior rows.

    S4 (2.0.0): the IEEE 29148 attributes `status`, `rationale`, `verification` and `parent`
    are columns, and `extra` holds every catalog key the reader does not map (JSON; NULL when
    there is none — absent, not empty).

    @brief Create the requirements table.
    @version 2
    """
    conn.execute("DROP TABLE IF EXISTS requirements")
    conn.execute(
        """
        CREATE TABLE requirements (
            id        TEXT PRIMARY KEY,
            block     TEXT,
            title     TEXT,
            acceptance TEXT,
            priority  TEXT,
            status    TEXT,
            rationale TEXT,
            verification TEXT,
            parent    TEXT,
            extra     TEXT
        )
        """,
    )
    conn.commit()


## @brief Create (or reset) the `requirement_links` table (GH #68).
## @version 1
## @dg_internal
def _create_links_table(conn: sqlite3.Connection) -> None:
    """ALWAYS CREATED, even with no catalogue: an empty table means "looked, no links"; an absent
    one means an index from before the layer.

    @brief Create the links table.
    """
    conn.execute("DROP TABLE IF EXISTS requirement_links")
    conn.execute(
        "CREATE TABLE requirement_links (req_id TEXT NOT NULL, satisfies TEXT NOT NULL, "
        "PRIMARY KEY (req_id, satisfies))"
    )
    conn.commit()


## A token of a `satisfies` value: anything that is not a separator, bracket or quote.
_LINK_TOKEN = re.compile(r"[^\s,\[\]'\"]+")


## @brief The requirement ids a `satisfies` value names, in every spelling a catalogue uses.
## @param value A list, one id, a comma-separated cell, or a list a loader already made text.
## @return The ids, in order, without duplicates.
## @version 1
## @req REQ-DDB-SCHEMA-015
def satisfies_ids(value: object) -> list[str]:
    """ONE NORMALISER for the index and the gate, so they never disagree about what an entry
    links to.

    @brief Normalise satisfies.
    @return Ids.
    """
    items = value if isinstance(value, list) else [value] if value else []
    out: list[str] = []
    for item in items:
        for tok in _LINK_TOKEN.findall(str(item)):
            if tok not in out:
                out.append(tok)
    return out


## @brief First present, non-empty value among several candidate keys.
## @param entry One catalog entry.
## @param keys Candidate keys, most specific first.
## @return The first truthy value, or None.
## @version 2
## @dg_internal
def _first(entry: dict, *keys: str) -> object | None:
    """ONE CATALOG, TWO VOCABULARIES. Our own flat shape says `{block, title, acceptance,
    priority}`; doxygen-guard's keyed YAML catalog says `{subsystem, name,
    acceptance_criteria}` with `name` as its only required field, and our extras move behind
    an `x-` prefix. Both are legitimate, and a repo that adopts the guard's shape
    is the normal case rather than an oddity.

    Reading one spelling only is what broke here: converting this repo's catalog to the keyed
    shape left every `requirements` row with a NULL title, block, acceptance and priority — 36
    rows present, all metadata gone. `req_trace` still returned implementers, so coverage read
    healthy while the catalog half was empty. That is the same failure shape as the catalog
    that would not load at all: the surface that is easy to check kept working.

    @brief Pick the first populated key from a candidate list.
    @return The value, or None when no candidate is present.
    @version 2
    """
    for key in keys:
        value = entry.get(key)
        if value:
            return value
    return None


## @brief Ingest one requirements entry into the requirements table.
## @param conn Open sqlite connection.
## @param entry One catalog mapping.
## @param id_col Declared/convention id column key.
## @param name_col Declared/convention title/name column key.
## @return 1 if a row was inserted, 0 if the entry had no id.
## v4 (2.0.0, S4): the 29148 columns, and every unmapped key kept in `extra` and logged.
## @version 4
## @req REQ-DDB-CONFIG-003
def _insert_req_entry(
    conn: sqlite3.Connection,
    entry: dict,
    id_col: str,
    name_col: str,
) -> int:
    """Insert a single flat catalog row, tolerating either the declared or
    the convention id/name keys.

    A KEY NO COLUMN READS IS KEPT, NOT DROPPED (2.0.0, S4): it lands verbatim in `extra` and the
    build log names it, so a catalog field the index does not model is visible rather than
    indistinguishable from one the catalog never had.

    @brief Insert one flat requirements-catalog row.
    @version 3
    """
    rid = entry.get(id_col) or entry.get("id")
    if not rid:
        return 0
    columns = {col: _first(entry, *keys) for col, keys in _COLUMN_KEYS.items()}
    columns["title"] = _first(entry, name_col, *_COLUMN_KEYS["title"])
    read = {
        id_col,
        "id",
        name_col,
        *_READ_ELSEWHERE,
        *(k for keys in _COLUMN_KEYS.values() for k in keys),
    }
    extra = {k: entry[k] for k in sorted(entry) if k not in read}
    if extra:
        logger.info(
            "requirements: %s carries keys no column reads, kept in `extra`: %s",
            rid,
            ", ".join(extra),
        )
    conn.execute(
        f"INSERT OR REPLACE INTO requirements (id, {', '.join(columns)}, extra) "
        f"VALUES (?, {', '.join('?' * len(columns))}, ?)",
        (
            rid,
            *(_scalar(v) for v in columns.values()),
            json.dumps(extra, default=str) if extra else None,
        ),
    )
    return 1


## Column -> the catalog keys that fill it, most specific first: our flat shape, doxygen-guard's
## keyed shape (`subsystem`, `acceptance_criteria`, `x-` extras) and the S4 (IEEE 29148) names.
_COLUMN_KEYS: dict[str, tuple[str, ...]] = {
    "block": ("block", "subsystem"),
    "title": ("name", "title"),
    "acceptance": ("acceptance", "acceptance_criteria"),
    "priority": ("priority", "x-priority"),
    "status": ("status", "x-status"),
    "rationale": ("rationale", "x-rationale"),
    "verification": ("verification", "verification_method", "x-verification"),
    "parent": ("parent", "x-parent"),
}
## Keys a different reader consumes: `satisfies` (requirement_links), `version` (the gate's
## version field). Not "unread", so not disclosed as such.
_READ_ELSEWHERE = ("satisfies", "version", "x-version")


## @brief A catalog value as a column holds it: text as written, a list or mapping as JSON.
## @param value The catalog value.
## @return Text, or None.
## @version 1
## @dg_internal
def _scalar(value: object) -> str | None:
    """@brief Column text. @return Text or None."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, default=str) if isinstance(value, (list, dict)) else str(value)


## The key under which doxygen-guard's catalog contract puts the requirement entries,
## and the field it requires on each. Both are DECLARED by `doxygen-guard config
## --schema` under `requirements_catalog` (root_key / required_fields), so these are the
## built-in defaults for a repo whose config cannot be read — never the whole policy.
CATALOG_ROOT_KEY = "requirements"


## @brief Requirement entries out of a mapping-keyed catalog, ID taken from the key.
## @param data Parsed catalog document.
## @return List of entry dicts each carrying an 'id', or [] when not this shape.
## @version 2
## @req REQ-DDB-CONFIG-003
def _keyed_req_entries(data: object) -> list[dict]:
    """Recognise the MAPPING-KEYED catalog: `{requirements: {REQ-X: {name: ...}}}`.

    doxygen-guard 1.3.1 adopted exactly this shape for its own catalog, and its schema
    says why — `formats_using_id_column` lists only `csv` and `json`, so a YAML catalog
    is keyed by ID and "the structure is self-describing", no `id_column` involved.

    THIS WAS MEASURED BEFORE IT WAS WRITTEN. Against the pinned public integration
    target, a 9,534-byte catalog of 22 requirements ingested ZERO rows, because
    `_is_flat_req_list` recognises only the flat `[{id, ...}, ...]` list. Nothing
    errored; the table was simply empty, which reads identically to a repo that has no
    catalog. That is the third time in this project that "no rows" was a claim about the
    DETECTOR rather than the data — the same shape as the macro-defined accessors and
    the causal layer once recorded as a correct negative.

    The ID comes from the key, so an entry that ALSO carries an id field is not merged:
    the key wins, because it is the thing the format is keyed on.

    @brief Flatten a mapping-keyed requirements catalog into entry dicts.
    @return Entries carrying 'id', or [] when the document is not this shape.
    @version 2
    """
    if not isinstance(data, dict):
        return []
    root = data.get(CATALOG_ROOT_KEY)
    if not isinstance(root, dict) or not root:
        return []
    return [{**value, "id": rid} for rid, value in root.items() if isinstance(value, dict) and rid]


## @brief Load a target repo's requirements.yaml into the requirements table.
## @param db_path Path to the clew.db being built.
## @param requirements_yaml Path to requirements.yaml, or None if absent.
## @param guard_cfg Parsed `guard:` section of .clew.yaml (declares column mapping), or None.
## v7: also `requirement_links` from each entry's `satisfies` (GH #68), created on every build.
## @version 7
## @req REQ-DDB-SCHEMA-015
## @req REQ-DDB-SCHEMA-006
def ingest_requirements_yaml(
    db_path: Path,
    requirements_yaml: Path | None,
    guard_cfg: dict | None = None,
) -> None:
    """Populate the `requirements` table from an OPTIONAL, format-tolerant
    requirements catalog.

    There is NO universal requirements.yaml format, so TWO declared shapes are read and
    nothing else is guessed:

      * the flat `[{id, ...}, ...]` list — CSV semantics in YAML syntax, keyed by the
        declared `impact.requirements.{id_column,name_column}` mapping when the guard
        config provides one, else the `{id, title, block, acceptance, priority}`
        convention;
      * the MAPPING-KEYED `{requirements: {REQ-X: {name: ...}}}` catalog, which is what
        doxygen-guard 1.3.1 itself now ships and what its schema implies by listing only
        csv/json under `formats_using_id_column`.

    Any other shape (e.g. a nested `domains:` catalog parsed only by that repo's own
    scripts) is logged and yields 0 catalog rows.

    The table is always created (possibly empty) so downstream `_has_table`-
    gated queries rely on a stable schema. An empty catalog is legitimate:
    `req_edges` (from `@req` tags) are the authoritative traceability, and
    LEFT JOINs to `requirements` already tolerate missing rows.

    @brief Ingest a flat or mapping-keyed requirements catalog; tolerate unknown shapes.
    @version 5
    """
    conn = sqlite3.connect(str(db_path))
    _create_requirements_table(conn)
    _create_links_table(conn)
    if requirements_yaml is None or not requirements_yaml.exists():
        conn.close()
        logger.info("requirements: no requirements.yaml found — table empty")
        return

    import yaml

    data = yaml.safe_load(requirements_yaml.read_text(encoding="utf-8"))
    id_col, name_col = resolve_catalog_columns(guard_cfg)

    entries = data if _is_flat_req_list(data, id_col) else _keyed_req_entries(data)
    if not entries:
        conn.close()
        logger.info(
            "requirements: %s is neither a flat id-bearing list nor a `%s:` mapping "
            "keyed by requirement id (nested or unrecognized catalog shape) — ingesting "
            "0 catalog rows; @req req_edges remain the authoritative traceability",
            requirements_yaml,
            CATALOG_ROOT_KEY,
        )
        return

    imported = 0
    for entry in entries:
        imported += _insert_req_entry(conn, entry, id_col, name_col)
        rid = entry.get(id_col) or entry.get("id")
        if rid:
            conn.executemany(
                "INSERT OR IGNORE INTO requirement_links (req_id, satisfies) VALUES (?, ?)",
                [(str(rid), target) for target in satisfies_ids(entry.get("satisfies"))],
            )
    conn.commit()
    conn.close()
    logger.info(
        "requirements: ingested %d requirements from %s",
        imported,
        requirements_yaml,
    )


## The punctuation doxygen appends when a tag ends a sentence or a list item. NOT a general
## strip set: exactly the characters a prose sentence terminates with, tried ONE at a time.
_SENTENCE_TAIL = ".,;:"


## @brief The req id a captured token denotes, allowing for doxygen's own trailing punctuation.
## @param token The id token as captured, e.g. 'REQ-PROBE-001.'.
## @param req_id_pattern The declared or permissive pattern the id must fully match.
## @return The matching id, or '' when the token denotes none.
## @version 1
## @req REQ-DDB-SCHEMA-006
## @dg_internal
def _matched_req_id(token: str, req_id_pattern: re.Pattern[str]) -> str:
    """GREEDY FIRST, AND THAT ORDER IS THE WHOLE SAFETY ARGUMENT (gh#20). A `@req` that
    follows `@brief` with no blank line continues the brief paragraph, and doxygen appends
    its own period when it closes that paragraph — so the captured token is
    `REQ-PROBE-001.` for a tag the author wrote cleanly, the full match fails, and the edge
    is dropped with no warning anywhere.

    Stripping punctuation unconditionally would be the wrong fix: a target's DECLARED
    pattern may legitimately contain dots (`REQ-1.2.3`), and this extractor's one hard
    guarantee is that every id matching today still matches. Trying the token as captured
    first means a dotted id matches on the first attempt and is never touched.

    ONE CHARACTER, ONCE. `REQ-X...` is prose this should decline, not a tag with three
    periods to peel — peeling until something matches is how a scanner starts inventing
    ids out of surrounding text.

    @brief Match a captured id token, tolerating one trailing sentence character.
    @return The id, or ''.
    @version 1
    """
    if req_id_pattern.match(token):
        return token
    if token[-1:] in _SENTENCE_TAIL:
        trimmed = token[:-1]
        if trimmed and req_id_pattern.match(trimmed):
            return trimmed
    return ""


## @brief Classify each `@req` tag occurrence into (req_id, confidence).
## @param text Doxygen description text to scan.
## @param req_id_pattern Compiled pattern the captured id token must match.
## @return list of (req_id, confidence) tuples whose id matched the pattern.
## @version 7
## @req REQ-DDB-SCHEMA-006
def _extract_req_tags(
    text: str | None,
    req_id_pattern: re.Pattern[str] = _PERMISSIVE_REQ_ID_RE,
) -> list[tuple[str, str]]:
    """Return every `@req <id>` occurrence in `text` whose `<id>`
    token FULLY matches `req_id_pattern` (the target repo's declared pattern,
    or the permissive default).

    The `@req` keyword is matched case-insensitively; the id token is kept
    verbatim so it round-trips against a case-sensitive declared pattern. An id
    is terminated by whitespace, by `<` (a doxygen markup boundary) or by
    end-of-text — see the `_REQ_TAG_TOKEN_RE` comment for the two silent
    failures the `<` terminator fixes.

    @brief Extract declared-pattern @req tags (literal + xrefitem-alias forms).
    @version 7
    """
    if not text:
        return []
    found: list[str] = []
    for match in _REQ_TAG_TOKEN_RE.finditer(text):
        req_id = _matched_req_id(match.group(1), req_id_pattern)
        if req_id:
            found.append(req_id)
    found.extend(_extract_xref_req_tags(text, req_id_pattern))
    return found


## @brief Extract req ids from doxygen `<xrefdescription>` blocks (aliased @req).
## @param text Doxygen description text (may contain xrefsect markup).
## @param req_id_pattern Compiled pattern the candidate token must match.
## @return list of (req_id, confidence) tuples for xref-embedded ids.
## @version 4
## @req REQ-DDB-SCHEMA-006
def _extract_xref_req_tags(
    text: str,
    req_id_pattern: re.Pattern[str],
) -> list[tuple[str, str]]:
    """Scan `<xrefdescription>` blocks for tokens matching the declared req id
    pattern — the form doxygen emits when `@req` is an xrefitem alias.

    Confined to xrefdescription content so prose mentions of an id elsewhere
    can't create phantom edges. An `[inferred]` marker inside the block maps
    to confidence 'inferred', else 'stated'.

    @brief Extract @req ids from doxygen xrefdescription blocks.
    @version 4
    """
    found: list[str] = []
    for block in _XREF_DESC_RE.findall(text):
        for token in _ID_TOKEN_RE.findall(block):
            ## Same tolerance as the literal form: an aliased tag rendered into an
            ## xrefdescription ends a sentence just as often as an unaliased one. The
            ## MATCHED id is appended, not the raw token — appending the token would store
            ## `REQ-X.` as the id and break the join to the catalog.
            req_id = _matched_req_id(token, req_id_pattern)
            if req_id:
                found.append(req_id)
    return found


## @brief Create (or reset) the `req_edges` table + indexes.
## @version 3
## @dg_internal
def _create_req_edges_table(conn: sqlite3.Connection) -> None:
    """Create the req_edges table schema, dropping any prior rows.

    @brief Create the req_edges table.
    @version 3
    """
    conn.execute("DROP TABLE IF EXISTS req_edges")
    conn.execute(
        """
        CREATE TABLE req_edges (
            req_id          TEXT NOT NULL,
            memberdef_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            UNIQUE(req_id, memberdef_rowid)
        )
        """,
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_req_edges_req_id ON req_edges(req_id)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_req_edges_memberdef ON req_edges(memberdef_rowid)",
    )
    conn.commit()


## @brief Parse requirement-reference doxygen tags out of function descriptions.
## @param db_path Path to the clew.db being built.
## @param req_id_pattern Declared requirement-id pattern (permissive default if None).
## @return None; writes rows into the req_edges table as a side effect.
## @version 5
## @req REQ-DDB-SCHEMA-006
def import_req_edges(
    db_path: Path,
    req_id_pattern: re.Pattern[str] | None = None,
) -> None:
    """Scan every function memberdef's brief/detailed description for `@req`
    tags whose id matches the target repo's DECLARED pattern (or the
    permissive fallback) and populate req_edges.

    A tag is simply an id — there is no confidence grading. That distinction was
    retired 2026-07-30: a requirement either has an implementer or it does not, and
    grading an author's confidence in their own tag added a second axis nobody read.
    Whether a requirement HAS an implementer is UNCHECKED — the pre-commit coverage
    audit that checked it is DELETED. This runs REGARDLESS of whether the
    requirements catalog parsed — tag edges are the authoritative traceability.

    @brief Import declared-pattern @req doxygen-tag edges into req_edges.
    @version 5
    """
    pattern = req_id_pattern or _PERMISSIVE_REQ_ID_RE
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _create_req_edges_table(conn)

    rows = conn.execute(
        """
        SELECT rowid, briefdescription, detaileddescription
        FROM memberdef
        WHERE kind = 'function'
        """,
    ).fetchall()

    imported = 0
    for row in rows:
        tags = _extract_req_tags(row["briefdescription"], pattern) + _extract_req_tags(
            row["detaileddescription"],
            pattern,
        )
        for req_id in tags:
            imported += conn.execute(
                "INSERT OR IGNORE INTO req_edges (req_id, memberdef_rowid) VALUES (?, ?)",
                (req_id, row["rowid"]),
            ).rowcount
    conn.commit()
    conn.close()
    logger.info("req_edges: imported %d @req tag edges", imported)


## @brief Decide whether a memberdef name/file looks like a test function.
## @param name Function name.
## @param file_path Indexed file path (relative to repo root).
## @return True if the name/path matches common test-function conventions.
## @version 1
## @dg_internal
def _looks_like_test_function(name: str, file_path: str | None) -> bool:
    """Test-name heuristic: `test_` prefix, or the file path contains 'test'.

    Kept in its own function so the heuristic is unit-testable in isolation
    from the table-population plumbing.

    @brief Test-function name/path heuristic.
    @version 1
    """
    if name.lower().startswith("test_"):
        return True
    return bool(file_path) and "test" in file_path.lower()


## @brief Create (or reset) the `req_test_edges` table.
## @version 1
## @dg_internal
def _create_req_test_edges_table(conn: sqlite3.Connection) -> None:
    """Create the req_test_edges table schema, dropping any prior rows.

    @brief Create the req_test_edges table.
    @version 1
    """
    conn.execute("DROP TABLE IF EXISTS req_test_edges")
    conn.execute(
        """
        CREATE TABLE req_test_edges (
            req_id             TEXT NOT NULL,
            test_memberdef_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            UNIQUE(req_id, test_memberdef_rowid)
        )
        """,
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_req_test_edges_req_id ON req_test_edges(req_id)",
    )
    conn.commit()


## @brief Materialize the test-function subset of req_edges into req_test_edges.
## @param db_path Path to the clew.db being built.
## @param test_patterns The resolved test-path patterns, or None for the name/path heuristic.
## v3 (round 4, R9): with patterns, a covering test is a function in a file they match — the
## substring heuristic made clew/testscope.py's `mark_test_scope` its own covering test.
## @version 3
## @req REQ-DDB-SCHEMA-006
def import_req_test_edges(db_path: Path, test_patterns: tuple[str, ...] | None = None) -> None:
    """Link test functions to requirements via req_edges → req_test_edges.

    For every req_edges row whose memberdef matches `_looks_like_test_function`,
    insert a (req_id, test_memberdef_rowid) row. This lets lookup_requirement
    cheaply distinguish "implementing functions" from "covering tests"
    without re-deriving the test-name heuristic at query time.

    @brief Materialize test-covering req_edges rows into req_test_edges.
    @version 2
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _create_req_test_edges_table(conn)

    if not _table_exists(conn, "req_edges"):
        conn.close()
        logger.info("req_test_edges: req_edges table absent — skipping")
        return

    rows = conn.execute(
        """
        SELECT re.req_id, re.memberdef_rowid, m.name, p.name AS file_path
        FROM req_edges re
        JOIN memberdef m ON m.rowid = re.memberdef_rowid
        LEFT JOIN path p ON p.rowid = m.file_id
        """,
    ).fetchall()

    imported = 0
    for row in rows:
        if test_patterns is not None:
            from .testscope import is_test_path

            if not is_test_path(str(row["file_path"] or ""), test_patterns):
                continue
        elif not _looks_like_test_function(row["name"], row["file_path"]):
            continue
        imported += conn.execute(
            """
            INSERT OR IGNORE INTO req_test_edges (req_id, test_memberdef_rowid)
            VALUES (?, ?)
            """,
            (row["req_id"], row["memberdef_rowid"]),
        ).rowcount
    conn.commit()
    conn.close()
    logger.info("req_test_edges: imported %d test-coverage edges", imported)


## @brief Return True if a table exists in the connected DB.
## @version 1
## @return True if a table with the given name exists in the connected DB, else False.
## @dg_internal
def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """Check whether a table exists (build-time equivalent of the docs
    server's `_has_table`).

    @brief Check for table presence.
    @version 1
    """
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
    )


## @brief The catalog path a repo DECLARES, when it declares one.
## @param guard_cfg Parsed `guard:` section of .clew.yaml, or None.
## @param repo_root Repo root the declared path is relative to.
## @return Resolved catalog path when declared and present, else None.
## v3: reads the top-level requirements: section (2.0.0, R5-CFG F7)
## @version 3
## @req REQ-DDB-SCHEMA-006
def declared_catalog_path(guard_cfg: dict | None, repo_root: Path) -> Path | None:
    """Honour `impact.requirements.file`, which the GATE already reads.

    doxygen-guard issue #7: "clew ignores `impact.requirements.file` and `.format`
    entirely, so a repo that declares where its catalog lives has that declaration honoured
    by the gate and ignored by the index." Measured true — the CLI took `--requirements` or
    nothing, so a repo that had said exactly where its catalog is still had to say it AGAIN
    on the command line, and through the MCP server (which passes no such flag) the
    declaration could never be honoured at all. That is the same argv-only hole
    `.clew.yaml` was created to close, left open on this one field.

    An explicit `--requirements` still WINS. The precedence is the repo's universal rule:
    CLI flag > declaration > nothing.

    Returns None rather than raising when the declared file is missing. A catalog is
    OPTIONAL metadata — `req_edges` populate from tags regardless — so a stale path should
    degrade to "no catalog" with a warning, not fail a build that has already run doxygen.

    @brief Resolve the declared requirements-catalog path, if any.
    @return Path when declared and present, else None.
    @version 2
    """
    declared = _declared_catalog_field(guard_cfg)
    if not declared:
        return None
    path = (repo_root / str(declared)).resolve()
    if not path.exists():
        logger.warning(
            "requirements: .clew.yaml declares requirements.file=%s but %s "
            "does not exist — ingesting no catalog; @req edges still populate from tags",
            declared,
            path,
        )
        return None
    logger.info("requirements: using DECLARED catalog requirements.file=%s", declared)
    return path


## The catalog locations a repo carries by convention when it declares nothing. A fallback
## rather than a rule, and ORDERED: the root comes first because every repo that resolves a
## catalog today resolves it there, and re-pointing those at a `docs/` copy would silently
## change which file an existing index was built from.
##
## `docs/` was added for gh#13. It is not a guess — it is where this pipeline ALREADY looks for
## a Doxyfile, so a repo that keeps its documentation inputs together was the reported case.
## Nothing further is added on speculation: a repo with any other layout has the DECLARATION,
## which outranks this tier and is the supported way to say where the catalog lives.
_CONVENTIONAL_CATALOGS = (
    "requirements.yaml",
    "docs/requirements.yaml",
)


## @brief The catalog path to ingest: declared first, then the conventional filename.
## @param guard_cfg Parsed `guard:` section of .clew.yaml, or None.
## @param repo_root Repo root both candidates are relative to.
## @return Resolved catalog path, or None when none exists.
## v3: reads the top-level requirements: section (2.0.0, R5-CFG F7)
## @version 3
## @req REQ-DDB-SCHEMA-006
def resolve_catalog_path(guard_cfg: dict | None, repo_root: Path) -> Path | None:
    """ONE RESOLVER, BECAUSE THERE WERE TWO AND THEY DISAGREED. `cli` resolved
    `--requirements or declared_catalog_path(...)` and never looked for the conventional
    file; the MCP server COMPOSED `repo/"requirements.yaml"` and passed it AS the flag — so
    through MCP the convention outranked the declaration, and through the CLI it did not
    exist at all. A repo with a root `requirements.yaml` AND a declared catalog elsewhere got
    a different catalog depending on which door the build came through, with no warning and
    two plausible-looking indexes.

    PRECEDENCE IS THE REPO'S UNIVERSAL RULE, extended by one step: explicit flag >
    declaration > convention > nothing. The flag stays above the declaration because someone
    typing a path means it; the convention goes BELOW because a file that merely happens to
    sit at the root is the weakest possible statement of intent — and `declared > whole repo`
    is the same precedence gh#333 settled for scope.

    The convention is kept rather than dropped: this repository, and most that adopt
    requirements traceability, put the catalog at the root and declare nothing. Deleting the
    composition without moving the discovery here would have silently stopped ingesting
    those catalogs — the `@req` edges would still populate from tags, so nothing would fail;
    the metadata would just quietly go missing.

    @brief Resolve the catalog path by declaration, then by convention.
    @return Catalog path, or None.
    @version 2
    """
    declared = declared_catalog_path(guard_cfg, repo_root)
    if declared is not None:
        return declared
    found = [rel for rel in _CONVENTIONAL_CATALOGS if (repo_root / rel).is_file()]
    if not found:
        return None
    ## NAMES THE LOSERS WHEN THERE ARE ANY. A silent pick is only safe when the caller can tell
    ## a pick was made, which is the rule `lookup_class` follows for compounds and `dossier` for
    ## overloads. Two conventional catalogs is a repository saying two different things, and the
    ## remedy — declare `impact.requirements.file` — is the one that makes the answer stable.
    if len(found) > 1:
        logger.warning(
            "requirements: %d conventional catalogs exist (%s) — using %s. Declare "
            "requirements.file to choose deliberately.",
            len(found),
            ", ".join(found),
            found[0],
        )
    else:
        logger.info("requirements: using CONVENTIONAL catalog %s", found[0])
    return repo_root / found[0]


## @brief The raw `requirements.file` value a config declares, if any.
## @param guard_cfg Parsed `guard:` section of .clew.yaml, or None.
## @return The declared path string, or '' when nothing is declared.
## v3: reads the top-level requirements: section (2.0.0, R5-CFG F7)
## @version 3
## @dg_internal
def _declared_catalog_field(guard_cfg: dict | None) -> str:
    """Split out purely to keep `declared_catalog_path` inside the max-3-returns
    standard, which the combined form breached at four.

    @brief Read the declared catalog path field.
    @return The declared value, or ''.
    @version 2
    """
    if not guard_cfg:
        return ""
    from .guard import config as dg_config

    return str(dg_config.get_requirements(guard_cfg).get("file") or "")


# --- catalogues read from a path or a pinned revision (GH #68) ------------------------------------

## A source that names a remote location rather than a local path or checkout.
_URLISH = re.compile(r"^[a-z][a-z0-9+.-]*://|^[\w.-]+@[\w.-]+:", re.I)


## @brief Run git in a local checkout through the hardened environment.
## @param cwd The checkout.
## @param args Git arguments.
## @return stdout, or None when git failed.
## @version 1
## @req REQ-DDB-GUARD-027
def git_text(cwd: Path, *args: str) -> str | None:
    """THE HARDENED ENVIRONMENT (`gitenv.git_argv`): a checkout's own config is data, never code.

    @brief Run git.
    @return Output or None.
    """
    import subprocess

    from .gitenv import git_argv

    try:
        out = subprocess.run(
            git_argv(*args), cwd=cwd, capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


## @brief Read a requirements catalogue from a local path or a pinned revision of a local checkout.
## @param repo_root The repository the source is relative to.
## @param source A path, or `{repo, rev, path}`.
## @return {requirement id: its row, values as text}.
## @version 1
## @req REQ-DDB-GUARD-027
def read_catalog_at(repo_root: Path | str, source: str | dict) -> dict[str, dict[str, str]]:
    """ONE READER for the gate's external catalogues and the wiki's pinned sub-catalogues (GH #68).

    A URL is REFUSED BY NAME (owner 2026-11-16): reading one would make a pre-commit gate depend
    on the network. A pinned source is read with `git show <rev>:<path>` from a LOCAL clone or
    submodule, so it is the catalogue as it was at that revision, not as the working tree has it.
    Both shapes are read — the `requirements:`-keyed mapping and the flat list of rows — and
    anything else raises rather than yielding an empty catalogue that would pass every tag.

    @brief Read a catalogue.
    @return Rows by id.
    """
    import yaml

    root = Path(repo_root)
    if isinstance(source, dict):
        missing = [k for k in ("repo", "rev", "path") if not source.get(k)]
        if missing:
            raise ValueError(f"a pinned catalogue needs repo, rev and path (missing: {missing})")
        _refuse_url(str(source["repo"]))
        text = git_text(root / str(source["repo"]), "show", f"{source['rev']}:{source['path']}")
        where = f"{source['repo']}@{source['rev']}:{source['path']}"
        if text is None:
            raise ValueError(f"catalogue {where} is not readable at that revision")
    else:
        _refuse_url(str(source))
        where = str(source)
        try:
            text = (root / where).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"catalogue {where} is not readable: {exc.strerror}") from exc
    try:
        rows = _catalog_rows(yaml.safe_load(text))
    except yaml.YAMLError as exc:
        raise ValueError(f"catalogue {where} is not YAML") from exc
    if not rows:
        raise ValueError(f"catalogue {where} holds no requirement rows")
    return rows


## @brief Refuse a source that is a URL.
## @param text The source.
## @return None.
## @version 1
## @dg_internal
def _refuse_url(text: str) -> None:
    """@brief URL check. @return None."""
    if _URLISH.match(text.strip()):
        raise ValueError(
            f"{text!r} is a URL: a catalogue is read from a local path or a local clone pinned "
            "by revision, never fetched"
        )


## @brief The rows of a parsed catalogue, in either shape.
## @param data The parsed document.
## @return {id: row}.
## @version 1
## @dg_internal
def _catalog_rows(data: object) -> dict[str, dict[str, str]]:
    """@brief Rows. @return Mapping."""
    if isinstance(data, dict) and isinstance(data.get("requirements"), dict):
        data = data["requirements"]
    out: dict[str, dict[str, str]] = {}
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict) and (row.get("id") or row.get("ID")):
                out[str(row.get("id") or row.get("ID"))] = {k: str(v) for k, v in row.items()}
    elif isinstance(data, dict):
        for key, row in data.items():
            if isinstance(row, dict) or row is None:
                out[str(key)] = {k: str(v) for k, v in (row or {}).items()}
    return out
