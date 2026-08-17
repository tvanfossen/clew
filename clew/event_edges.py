# SPDX-License-Identifier: MIT
"""Author-DECLARED event edges, recovered from doxygen xrefitem aliases.

A repo that documents its event bus with tags like `@emits EVENT:FOO` /
`@handles EVENT:FOO` has already written down its producer→consumer graph, and
doxygen has already stored it: an `ALIASES = "emits=@xrefitem evt_emits ..."`
declaration makes doxygen rewrite each tag into an `<xrefsect>` whose
`<xrefdescription>` carries the topic. That is the SAME mechanism
`requirements.py` already mines for aliased `@req` — so the event catalog sits
in every such database, fully formed, and was simply never read.

Nothing here is inferred. Unlike `shared_key_edges`' pattern matching, which
guesses that two functions touching a like-named accessor are related, an
`@emits`/`@handles` pair is an assertion the author made and, where a gate runs,
pre-commit enforces. That makes these the highest-confidence causal edges the
pipeline can produce, and they land as `declared=1`.

NO HARDCODING (CLAUDE.md): the xrefitem KEY (`evt_emits`) is repo-chosen, so it
is never assumed — it is read from the target's own `ALIASES` declaration. Only
the TAG NAME the author writes (`emits`/`handles`) is interpreted, via a
built-in default vocabulary plus the target's own `event_tags:` declaration,
which REPLACES it. A repo whose Doxyfile declares no recognised event alias
yields zero rows: a correct negative, not an error — but never a silent one,
because `_report_unrecognised_aliases` names the tags it did not claim.

Edges land in `shared_key_edges` rather than a new table, because that is what
they are — a topic is a key, an emitter is a writer, a handler is a reader —
and `edge_kind='event'` was already an allowed value there that nothing had
ever written. Landing them there means `chain_trace` crosses event seams with
no query-layer change at all, and (running before `annotate_thread_boundaries`)
they pick up `crosses_thread`/`to_thread_id` for free.

@brief Import author-declared @emits/@handles event edges.
@version 2
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

PRODUCER = "producer"
CONSUMER = "consumer"

# Built-in vocabulary for the TAG NAME an author writes (`@emits`). Repo-chosen
# xrefitem keys are never guessed — see the module docstring. A target using
# different words states its own in `.clew.yaml`'s `event_tags:` section
# (declaration.SECTION_EVENT_TAGS), which REPLACES this list rather than extending
# it — `raises` below is why that matters, being an EXCEPTION verb nearly
# everywhere outside an event bus.
DEFAULT_EVENT_TAGS: dict[str, str] = {
    "emits": PRODUCER,
    "emit": PRODUCER,
    "publishes": PRODUCER,
    "publish": PRODUCER,
    "produces": PRODUCER,
    "sends": PRODUCER,
    "raises": PRODUCER,
    "fires": PRODUCER,
    "posts": PRODUCER,
    "handles": CONSUMER,
    "handle": CONSUMER,
    "subscribes": CONSUMER,
    "subscribe": CONSUMER,
    "consumes": CONSUMER,
    "receives": CONSUMER,
    "listens": CONSUMER,
    "observes": CONSUMER,
}

# `ALIASES = "emits=@xrefitem evt_emits \"Emits ingot event\" \"...\""` — capture
# the author-facing tag name and the xrefitem key doxygen will stamp into the id.
_ALIAS_RE = re.compile(r'"\s*(\w+)\s*=\s*@xrefitem\s+(\w+)', re.IGNORECASE)

# `<xrefsect id="evt_emits_1_evt_emits000029">…<xrefdescription>TOPIC</…>`.
# The id is captured whole and matched against the DECLARED keys rather than
# parsed structurally, so a doxygen change to the id shape cannot silently
# mis-attribute a section.
_XREFSECT_RE = re.compile(
    r'<xrefsect\s+id="([^"]+)".*?<xrefdescription>(.*?)</xrefdescription>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


## @brief Reduce an xrefdescription payload to its bare topic token.
## @param raw Inner text of an <xrefdescription> block.
## @return Whitespace-normalised topic text ("" when the block is empty).
## @version 1
## @dg_internal
def _topic(raw: str) -> str:
    """@brief Strip markup and collapse whitespace to yield the topic token."""
    return " ".join(_TAG_RE.sub(" ", raw).split())


## @brief Name the aliased tags no active vocabulary claims, so an owner can declare them.
## @param tags Tag names found in ALIASES that resolved to no event role.
## @return None.
## @version 1
## @dg_internal
def _report_unrecognised_aliases(tags: list[str]) -> None:
    """The #29 undeclared-accessor diagnostic, applied to the event layer: a repo
    whose bus is documented `@broadcasts`/`@reacts` produced zero rows and said
    NOTHING, which is indistinguishable from a repo that has no event bus. This
    turns that silence into the one actionable sentence — here are the words you
    used, here is where to claim them.

    Every non-event alias a repo has is listed too (`req` is the common one), and
    that is deliberate rather than sloppy: nothing in an ALIASES line marks a tag
    as belonging to an event bus, so filtering would mean guessing, and guessing
    wrong here hides exactly the tag the owner needed to see. The wording asks a
    question instead of asserting a defect, so a listed `req` reads as noise
    rather than as a finding.

    @brief Log the aliased tags no active event vocabulary recognises.
    @version 1
    """
    if not tags:
        return
    logger.info(
        "event edges: %d xrefitem alias(es) are not recognised event verbs (%s) — if any "
        "of these names this repo's event bus, declare `event_tags: {<tag>: producer}` "
        "(or consumer) in .clew.yaml to read it; a declared vocabulary REPLACES "
        "the built-in verbs (%s)",
        len(tags),
        ", ".join(tags),
        ", ".join(sorted(DEFAULT_EVENT_TAGS)),
    )


## @brief Split a target's xrefitem ALIASES into claimed event keys and unclaimed tags.
## @param doxyfile Target repo's Doxyfile (the one carrying its ALIASES).
## @param event_tags Declared tag-name → role vocabulary REPLACING the defaults, or None.
## @return (xrefitem key → PRODUCER/CONSUMER, sorted tuple of tag names no role claimed).
## @version 1
## @req REQ-DDB-CONFIG-007
def classify_aliases(
    doxyfile: Path, event_tags: dict[str, str] | None
) -> tuple[dict[str, str], tuple[str, ...]]:
    """BOTH HALVES RETURNED, because both are answers. The claimed keys drive the
    import; the unclaimed tags are the only evidence a reader gets that this repo
    documents a bus in words the active vocabulary does not know.

    Split out of `_declared_event_keys` for gh#320 so the diagnostic can be reported
    as DATA and not only logged. It is pure apart from reading one file, which is what
    lets the stamp site re-derive it instead of threading a metadata value back out
    through the importer — the choice `cli` already documents for `key_alias_prefixes`.
    Re-deriving is only safe because nothing in the database can disagree with it: the
    unclaimed tags produce no rows, by definition.

    An unreadable Doxyfile is a correct negative, not an error — a synthesised Doxyfile
    (#33) legitimately has no ALIASES, and reports zero of each.

    @brief Classify a repo's ALIASES against the active event vocabulary.
    @return Claimed keys and unclaimed tag names.
    @version 1
    """
    vocabulary = event_tags if event_tags is not None else DEFAULT_EVENT_TAGS
    try:
        text = doxyfile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ()
    keys: dict[str, str] = {}
    unrecognised: set[str] = set()
    for tag, key in _ALIAS_RE.findall(text):
        role = vocabulary.get(tag.lower())
        if role in (PRODUCER, CONSUMER):
            keys[key] = role
        else:
            unrecognised.add(tag)
    return keys, tuple(sorted(unrecognised))


## @brief Map declared xrefitem keys to an event role using the tag vocabulary.
## @param doxyfile Target repo's Doxyfile (the one carrying its ALIASES).
## @param event_tags Declared tag-name → role vocabulary REPLACING the defaults, or None.
## @return Mapping of xrefitem key → PRODUCER/CONSUMER; empty when none is declared.
## @version 3
## @dg_internal
def _declared_event_keys(doxyfile: Path, event_tags: dict[str, str] | None) -> dict[str, str]:
    """Read the target's own ALIASES and keep only the aliases whose TAG NAME
    is a recognised event verb. The key (`evt_emits`) is whatever the repo
    chose; the tag (`emits`) is what carries meaning, so only the tag is
    interpreted.

    A declared vocabulary REPLACES the built-in one instead of extending it. That
    is what makes `raises` survivable: it is a default PRODUCER verb here and an
    EXCEPTION verb in most codebases, so a repo aliasing `raises=@xrefitem
    exceptions ...` has its exception documentation mined as event production, and
    only stating the whole vocabulary can take it back.

    The classification itself moved to `classify_aliases`; this keeps the LOGGING,
    which is the half a build operator watching stdout still wants.
    """
    keys, unrecognised = classify_aliases(doxyfile, event_tags)
    _report_unrecognised_aliases(list(unrecognised))
    return keys


## @brief Collect every (topic, role, name, rowid, is_definition) tag occurrence.
## @param conn Open connection to the database being built.
## @param keys Declared xrefitem key → role mapping.
## @return One tuple per declared event tag found on a memberdef.
## @version 4
## @dg_internal
def _harvest_tagged(
    conn: sqlite3.Connection, keys: dict[str, str]
) -> list[tuple[str, str, str, int, bool]]:
    """Scan memberdef descriptions for xrefsects belonging to a declared event
    key, keeping the ROWID that actually carried the tag.

    Carrying the rowid is load-bearing. Resolving the tag's function NAME back
    through a name index instead is badly wrong, because `memberdef.name` is
    UNQUALIFIED: in an FSM-per-state codebase a name like `react` maps to dozens of
    memberdefs (one per FSM
    class) of which exactly ONE declares an `@emits`. Name-expanding that tag
    fabricated an edge for the other 59 — measured 5294 edges where 175 are
    real. An edge is only ever attributed to a memberdef that declared it.
    """
    found: list[tuple[str, str, str, int, bool]] = []
    rows = conn.execute(
        "SELECT rowid, name, (file_id = bodyfile_id), detaileddescription FROM memberdef "
        "WHERE kind='function' AND detaileddescription IS NOT NULL"
    ).fetchall()
    for rowid, name, is_def, desc in rows:
        for sect_id, payload in _XREFSECT_RE.findall(desc):
            role = next((r for k, r in keys.items() if sect_id.startswith(k)), None)
            topic = _topic(payload)
            if role is not None and topic:
                found.append((topic, role, name, rowid, bool(is_def)))
    return found


## @brief Collapse decl/def duplicates into one rowid set per topic and role.
## @param tagged Tag occurrences from _harvest_tagged.
## @return Mapping of topic → role → rowids.
## @version 2
## @req REQ-DDB-SCHEMA-009
def _topic_roles(
    tagged: list[tuple[str, str, str, int, bool]],
) -> dict[str, dict[str, set[int]]]:
    """Doxygen documents one function twice when it is declared in a header and
    defined in a .cpp, so the SAME logical emitter can carry the tag on two
    rowids. Collapse per (topic, role, name), preferring the definition row —
    but only ever among rows that carried the tag, never widening to untagged
    same-named functions.
    """
    grouped: dict[tuple[str, str, str], list[tuple[int, bool]]] = {}
    for topic, role, name, rowid, is_def in tagged:
        grouped.setdefault((topic, role, name), []).append((rowid, is_def))
    topics: dict[str, dict[str, set[int]]] = {}
    for (topic, role, _name), entries in grouped.items():
        defs = [r for r, is_def in entries if is_def]
        chosen = defs if defs else [r for r, _ in entries]
        bucket = topics.setdefault(topic, {PRODUCER: set(), CONSUMER: set()})
        bucket[role].update(chosen)
    return topics


## @brief Expand topic buckets into (emitter_rowid, handler_rowid, topic) triples.
## @param topics Topic → role → rowids, from _topic_roles.
## @return Deduplicated edge triples ready for insertion.
## @version 3
## @req REQ-DDB-SCHEMA-009
def _edges_for(topics: dict[str, dict[str, set[int]]]) -> list[tuple[int, int, str]]:
    """Every emitter of a topic is paired with every handler of it. This is the
    same honesty level as `shared_key_edges`: sharing a topic proves a POSSIBLE
    causal path, not that a specific emit reached a specific handler — no
    static reading of a decoupled bus can prove the latter. A topic with only
    emitters (or only handlers) yields no edge; those one-sided topics are
    reported by the caller as a diagnostic, since an event emitted but never
    handled is usually a real defect.
    """
    edges: set[tuple[int, int, str]] = set()
    for topic, bucket in topics.items():
        for erow in bucket[PRODUCER]:
            for hrow in bucket[CONSUMER]:
                edges.add((erow, hrow, topic))
    return sorted(edges)


## @brief Log the one-sided topics that indicate a likely defect.
## @param topics Topic → role → rowids.
## @return None.
## @version 2
## @dg_internal
def _report_one_sided(topics: dict[str, dict[str, set[int]]]) -> None:
    """An emitted-but-unhandled topic (or a handler nobody emits) is a free
    owner diagnostic that falls straight out of the catalog — surfaced at
    WARNING because it usually means dead code or a missed subscription.
    """
    unhandled = sorted(t for t, b in topics.items() if b[PRODUCER] and not b[CONSUMER])
    unemitted = sorted(t for t, b in topics.items() if b[CONSUMER] and not b[PRODUCER])
    if unhandled:
        logger.warning(
            "event topics emitted but NEVER handled (%d): %s", len(unhandled), ", ".join(unhandled)
        )
    if unemitted:
        logger.warning(
            "event topics handled but NEVER emitted (%d): %s", len(unemitted), ", ".join(unemitted)
        )


## @brief Import author-declared @emits/@handles event edges into shared_key_edges.
## @param db_path Database being built.
## @param doxyfile Target repo's Doxyfile, read for its ALIASES declaration.
## @param event_tags The target's declared tag-name → role vocabulary, REPLACING
##        DEFAULT_EVENT_TAGS; None keeps the defaults. Supplied by `cli._build_stages`
##        from `declaration.declared_event_tags` — there is no CLI flag.
## @return None.
## @version 2
## @req REQ-DDB-SCHEMA-009
def import_event_edges(
    db_path: Path,
    doxyfile: Path,
    event_tags: dict[str, str] | None = None,
) -> None:
    """Recover the event graph the author already declared.

    Rows land as `edge_kind='event'`, `declared=1`,
    `source='shared_key_declared'`, `dispatch_mode='keyed'` (a topic-keyed bus)
    and `edge_triggered=1` (an event is edge-triggered by definition — the
    first time anything populates that column). Runs before
    `annotate_thread_boundaries`, so these edges also acquire
    crosses_thread/to_thread_id.

    @brief Import declared event edges.
    @version 2
    """
    keys = _declared_event_keys(Path(doxyfile), event_tags)
    if not keys:
        logger.info("event edges: no event xrefitem alias declared — skipping (correct negative)")
        return
    conn = sqlite3.connect(db_path)
    try:
        topics = _topic_roles(_harvest_tagged(conn, keys))
        edges = _edges_for(topics)
        conn.executemany(
            "INSERT OR IGNORE INTO shared_key_edges "
            "(writer_rowid, reader_rowid, key_name, edge_kind, declared, source, "
            " confidence, dispatch_mode, edge_triggered) "
            "VALUES (?, ?, ?, 'event', 1, 'shared_key_declared', 'high', 'keyed', 1)",
            edges,
        )
        conn.commit()
        _report_one_sided(topics)
        logger.info(
            "event edges: %d topics from %d declared alias(es) → %d edges",
            len(topics),
            len(keys),
            len(edges),
        )
    finally:
        conn.close()
