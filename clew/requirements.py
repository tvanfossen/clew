# SPDX-License-Identifier: MIT
"""Requirements traceability: requirements.yaml ingestion + `@req` edges.

Three stages, run after the call-graph layers and before reachability:

  1. `ingest_requirements_yaml` — loads a target repo's OPTIONAL, format-
     tolerant `requirements.yaml`. Ingests only the flat `[{id, ...}]` shape
     (id/name columns via the repo's DECLARED `.doxygen-guard.yaml`
     `impact.requirements` mapping when present, else the {id,title,...}
     convention). Nested/unknown catalogs (e.g. a `domains:` tree) yield 0
     rows — the structure is never guessed. No universal format is assumed.

  2. `import_req_edges` — scans `memberdef.briefdescription` and
     `memberdef.detaileddescription` for `@req <id>` tags, keeping ids that
     match the target repo's DECLARED pattern
     (`.doxygen-guard.yaml` `validate.tags.req.pattern`) or a permissive
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
# (no .doxygen-guard.yaml, or no validate.tags.req.pattern). Deliberately NOT
# the old hardcoded `REQ-\d+` — it accepts any `REQ-<alnum>...` id (demobot's
# `REQ-0621`, `REQ-PROJ-NAV-002`, etc.) so req_edges populate for any
# repo that has not declared a stricter shape.
_PERMISSIVE_REQ_ID_RE = re.compile(r"^REQ-[A-Za-z0-9][A-Za-z0-9_-]*$")


## @brief Load a target repo's .doxygen-guard.yaml (declaration source).
## @param guard_config_path Path to the repo's .doxygen-guard.yaml, or None.
## @param repo_root Repo root, so a version skew can name the rev the target pins.
## @return Parsed config dict, or None if absent / unusable.
## @version 6
## @req REQ-DDB-CONFIG-001
def load_guard_config(
    guard_config_path: Path | None, repo_root: Path | str | None = None
) -> dict | None:
    """Load a repo's `.doxygen-guard.yaml` through `guardconfig.read_guard_config`.

    Single source of the config load so both the `@req` pattern resolution
    and the catalog column mapping read from ONE parsed dict. Returns None
    (not an error) when there is no config to read — every declaration-driven
    lookup then falls back to its permissive built-in default.

    THE READ IS PERMISSIVE (gh#32). It used to call `doxygen_guard.config.load_config`
    directly, which is a GATE's loader: one key from another doxygen-guard release and
    the whole document was refused, taking the declared `@req` id pattern and catalog
    mapping with it. A target pins its own release and we pin ours, so that is the
    normal case at scale rather than an authoring error — `read_guard_config` drops the
    keys we never read, keeps the ones we do, and reports the skew as a skew.

    The `SystemExit` arm that used to live here moved with the load; the note on why it
    is kept is in `guardconfig._strict_load`.

    @brief Load the target repo's declared doxygen-guard config, tolerating skew.
    @version 6
    """
    if guard_config_path is None or not guard_config_path.exists():
        return None
    from .guardconfig import read_guard_config

    read = read_guard_config(guard_config_path, repo_root)
    return read.config if read.usable() else None


## The unusable-config warning MOVED to `guardconfig._warn_unusable` with the load it
## belongs to (gh#32). It is one function, not two, for the same reason discovery is one
## function: two copies of "what happens when the guard config cannot be used" is how one
## consumer ends up tolerant and the other fatal on the same file.


## @brief Resolve the target repo's DECLARED `@req` id pattern (or fallback).
## @param guard_cfg Parsed .doxygen-guard.yaml dict, or None.
## @return Compiled regex the captured `@req` id token must fully match.
## @version 2
## @req REQ-DDB-CONFIG-001
def resolve_req_id_pattern(guard_cfg: dict | None) -> re.Pattern[str]:
    """Return the compiled `validate.tags.req.pattern` from the guard config.

    When no config or no declared pattern is present, fall back to the
    PERMISSIVE default — never to a hardcoded per-repo format.

    @brief Resolve the declared @req id pattern (permissive fallback).
    @version 2
    """
    if guard_cfg:
        from doxygen_guard import config as dg_config

        validate = dg_config.get_validate(guard_cfg)
        declared = (validate.get("tags", {}).get("req", {}) or {}).get("pattern")
        if declared:
            logger.info("requirements: using declared @req id pattern %r", declared)
            return re.compile(declared)
    return _PERMISSIVE_REQ_ID_RE


## @brief Resolve the DECLARED requirements-catalog id/name column names.
## @param guard_cfg Parsed .doxygen-guard.yaml dict, or None.
## @return (id_column, name_column) — declared mapping or {id,title} default.
## @version 3
## @req REQ-DDB-CONFIG-001
def resolve_catalog_columns(guard_cfg: dict | None) -> tuple[str, str]:
    """Return the id/name column keys for a flat requirements catalog.

    Reads `impact.requirements.{id_column,name_column}` when the guard config
    declares them (matching how doxygen-guard itself reads the catalog);
    otherwise the clew convention `{id, title}`.

    @brief Resolve declared catalog id/name columns (id/title default).
    @version 3
    """
    id_col, name_col = "id", "title"
    if guard_cfg:
        from doxygen_guard import config as dg_config

        req = dg_config.get_impact(guard_cfg).get("requirements") or {}
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
## @version 1
## @dg_internal
def _create_requirements_table(conn: sqlite3.Connection) -> None:
    """Create the requirements table schema, dropping any prior rows.

    @brief Create the requirements table.
    @version 1
    """
    conn.execute("DROP TABLE IF EXISTS requirements")
    conn.execute(
        """
        CREATE TABLE requirements (
            id        TEXT PRIMARY KEY,
            block     TEXT,
            title     TEXT,
            acceptance TEXT,
            priority  TEXT
        )
        """,
    )
    conn.commit()


## @brief First present, non-empty value among several candidate keys.
## @param entry One catalog entry.
## @param keys Candidate keys, most specific first.
## @return The first truthy value, or None.
## @version 1
## @dg_internal
def _first(entry: dict, *keys: str) -> object | None:
    """ONE CATALOG, TWO VOCABULARIES. Our own flat shape says `{block, title, acceptance,
    priority}`; doxygen-guard's keyed YAML catalog says `{subsystem, name,
    acceptance_criteria}` with `name` as its only required field, and our extras move behind
    the `x-` passthrough prefix. Both are legitimate, and a repo that adopts the guard's shape
    is the normal case rather than an oddity.

    Reading one spelling only is what broke here: converting this repo's catalog to the keyed
    shape left every `requirements` row with a NULL title, block, acceptance and priority — 36
    rows present, all metadata gone. `req_trace` still returned implementers, so coverage read
    healthy while the catalog half was empty. That is the same failure shape as the catalog
    that would not load at all: the surface that is easy to check kept working.

    @brief Pick the first populated key from a candidate list.
    @return The value, or None when no candidate is present.
    @version 1
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
## @version 3
## @req REQ-DDB-CONFIG-003
def _insert_req_entry(
    conn: sqlite3.Connection,
    entry: dict,
    id_col: str,
    name_col: str,
) -> int:
    """Insert a single flat catalog row, tolerating either the declared or
    the convention id/name keys.

    @brief Insert one flat requirements-catalog row.
    @version 2
    """
    rid = entry.get(id_col) or entry.get("id")
    if not rid:
        return 0
    conn.execute(
        """
        INSERT OR REPLACE INTO requirements (id, block, title, acceptance, priority)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            rid,
            _first(entry, "block", "subsystem"),
            _first(entry, name_col, "name", "title"),
            _first(entry, "acceptance", "acceptance_criteria"),
            _first(entry, "priority", "x-priority"),
        ),
    )
    return 1


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
## @param guard_cfg Parsed .doxygen-guard.yaml dict (declares column mapping), or None.
## @version 6
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
    conn.commit()
    conn.close()
    logger.info(
        "requirements: ingested %d requirements from %s",
        imported,
        requirements_yaml,
    )


## @brief Classify each `@req` tag occurrence into (req_id, confidence).
## @param text Doxygen description text to scan.
## @param req_id_pattern Compiled pattern the captured id token must match.
## @return list of (req_id, confidence) tuples whose id matched the pattern.
## @version 6
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
    @version 6
    """
    if not text:
        return []
    found: list[str] = []
    for match in _REQ_TAG_TOKEN_RE.finditer(text):
        req_id = match.group(1)
        if req_id_pattern.match(req_id):
            found.append(req_id)
    found.extend(_extract_xref_req_tags(text, req_id_pattern))
    return found


## @brief Extract req ids from doxygen `<xrefdescription>` blocks (aliased @req).
## @param text Doxygen description text (may contain xrefsect markup).
## @param req_id_pattern Compiled pattern the candidate token must match.
## @return list of (req_id, confidence) tuples for xref-embedded ids.
## @version 3
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
    @version 3
    """
    found: list[str] = []
    for block in _XREF_DESC_RE.findall(text):
        for token in _ID_TOKEN_RE.findall(block):
            if req_id_pattern.match(token):
                found.append(token)
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
## @version 2
## @req REQ-DDB-SCHEMA-006
def import_req_test_edges(db_path: Path) -> None:
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
        if not _looks_like_test_function(row["name"], row["file_path"]):
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
## @param guard_cfg Parsed .doxygen-guard.yaml dict, or None.
## @param repo_root Repo root the declared path is relative to.
## @return Resolved catalog path when declared and present, else None.
## @version 1
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
    @version 1
    """
    declared = _declared_catalog_field(guard_cfg)
    if not declared:
        return None
    path = (repo_root / str(declared)).resolve()
    if not path.exists():
        logger.warning(
            "requirements: .doxygen-guard.yaml declares impact.requirements.file=%s but %s "
            "does not exist — ingesting no catalog; @req edges still populate from tags",
            declared,
            path,
        )
        return None
    logger.info("requirements: using DECLARED catalog impact.requirements.file=%s", declared)
    return path


## The catalog filename a repo carries by convention when it declares nothing. The ONE
## conventional path in this pipeline, and it is a fallback rather than a rule.
_CONVENTIONAL_CATALOG = "requirements.yaml"


## @brief The catalog path to ingest: declared first, then the conventional filename.
## @param guard_cfg Parsed .doxygen-guard.yaml dict, or None.
## @param repo_root Repo root both candidates are relative to.
## @return Resolved catalog path, or None when neither exists.
## @version 1
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
    @version 1
    """
    declared = declared_catalog_path(guard_cfg, repo_root)
    if declared is not None:
        return declared
    conventional = repo_root / _CONVENTIONAL_CATALOG
    if conventional.is_file():
        logger.info("requirements: using CONVENTIONAL catalog %s", _CONVENTIONAL_CATALOG)
        return conventional
    return None


## @brief The raw `impact.requirements.file` value a config declares, if any.
## @param guard_cfg Parsed .doxygen-guard.yaml dict, or None.
## @return The declared path string, or '' when nothing is declared.
## @version 1
## @dg_internal
def _declared_catalog_field(guard_cfg: dict | None) -> str:
    """Split out purely to keep `declared_catalog_path` inside the max-3-returns
    standard, which the combined form breached at four.

    @brief Read the declared catalog path field.
    @return The declared value, or ''.
    @version 1
    """
    if not guard_cfg:
        return ""
    from doxygen_guard import config as dg_config

    return str((dg_config.get_impact(guard_cfg).get("requirements") or {}).get("file") or "")
