# SPDX-License-Identifier: MIT
"""R2 access to the configuration space (gh#18): what variants this firmware has.

"What configurations does this firmware have?" had no answer before gh#18 — not a
partial one, no table to hold it. This module is the read side.

## THE REPLY ALWAYS SAYS WHY IT IS EMPTY

Three different repositories produce zero symbols here: one with no Kconfig, one
whose Kconfig declares nothing, and one whose Kconfig could not be parsed (a Zephyr
application indexed outside its west workspace, which is ordinary rather than
exotic). `KconfigSpace` carries `found`, `source` and `error` so a consumer can tell
them apart, because this repo's standing lesson is that "no rows" is a claim about
the DETECTOR until you have checked whether the detector could look — and a query
surface that returns a bare empty list invites the flattering reading.

## STRUCTURE AND INSTANCE, TOGETHER BUT LABELLED

`configured_macros` reports gh#17's `preprocessor.predefined` beside the space. The
two must travel together — an agent that reads a `default` without knowing which
variant the index was built in will describe the default as what the firmware does
— and they must stay LABELLED, because a `default` is a property of the repository
while a configured macro is a property of this one index.

@brief Query a repo's Kconfig configuration space and its gating sites.
@version 1
"""

from __future__ import annotations

import sqlite3

from ..vocabulary import LAYER_STATE_ABSENT, LAYER_STATE_EMPTY, LAYER_STATE_POPULATED
from ._common import DbSource, connect, has_columns, table_exists
from .models import KconfigEntry, KconfigGate, KconfigSpace

## The `build_meta` prefix `kconfig.as_meta` writes under. Spelled here rather than
## imported from `kconfig.py`, which pulls in `kconfiglib` and the whole pipeline —
## `query/` is stdlib-only by design, and a read surface must not need the parser.
_META_PREFIX = "kconfig."

## gh#17's key for the macro list this index was built with. Read here so structure
## and instance arrive in one reply rather than requiring a consumer to know that two
## unrelated-looking `build_meta` namespaces have to be joined by hand.
_PREPROCESSOR_MACROS = "preprocessor.predefined"

## WHERE `configured_macros` CAME FROM, and the route to the repository's own default.
##
## Both are read because `configured_macros` alone is a claim a reader inverts. Measured on
## Mbed-TLS/mbedtls 2026-08-14: the acceptance build states `MBEDTLS_THREADING_C` and
## `MBEDTLS_THREADING_PTHREAD` as PREDEFINED so doxygen can reach the guarded bodies, and every
## reply then reported them as `configured_macros` with all 154 gate rows labelled
## `origin: "declared"`. The repository ships both COMMENTED OUT
## (`include/mbedtls/mbedtls_config.h:3787` and `:2196`), so an agent reading the payload
## concluded the exact opposite of the truth — on two graded marks, through both `search` and
## `dossier`, because they share this payload.
##
## `preprocessor.source` already distinguishes the two cases and nothing surfaced it:
## `declared` means an operator stated the macros for this build, `config_header` means they
## were read out of the repository's own header (a fact ABOUT the repository), and
## `declared+config_header` means both. `preprocessor.config_header` names that header when it is
## known, which is what turns a disclaimer into a route.
_PREPROCESSOR_SOURCE = "preprocessor.source"
_PREPROCESSOR_HEADER = "preprocessor.config_header"

## The macros the OPERATOR stated that the repository's own header does NOT define — written by
## `PreprocessorConfig.as_meta`. This is what turns the mixed case from a caveat into an answer:
## a name here ships OFF, and every other macro in `configured_macros` was read from the header
## and therefore ships ON. Absent on an index built before it, which reads as "this build did not
## record the split" rather than as "nothing was stated".
_PREPROCESSOR_STATED_ONLY = "preprocessor.stated_only"


## @brief Say what `configured_macros` is evidence OF, and route to the repo's own default.
## @param macros The stated macro list, verbatim.
## @param source `preprocessor.source`: declared / config_header / declared+config_header.
## @param header `preprocessor.config_header`, repo-relative, or "" when unknown.
## @param stated_only Names the operator supplied that the repo's own header does not define.
## @return A sentence for the reply, or "" when no configuration was recorded at all.
## @version 3
## @req REQ-DDB-QUERY-006
def macros_meaning(macros: str, source: str, header: str, stated_only: str = "") -> str:
    """ROUTE, DO NOT DISCLAIM — this repo's standing pattern, and the reason it is needed here
    is that the previous reply argued for a FALSE answer rather than merely withholding a true
    one. `configured_macros` says which variant the INDEX was built in. A reader takes it for
    which variant the REPOSITORY ships, and on a target whose macros were stated by the operator
    those are opposites.

    Measured on mbedtls: the acceptance build predefines `MBEDTLS_THREADING_C` and
    `MBEDTLS_THREADING_PTHREAD`; the shipped `include/mbedtls/mbedtls_config.h` has both
    commented out. Two graded marks ask for the shipped state, and every reply pointed the other
    way — including all 154 gate rows, labelled `origin: "declared"`, where "declared" means
    "named in the list THIS BUILD was given" and reads as "the repository declares it".

    A DISCLAIMER WOULD NOT HAVE HELPED. "these macros may not reflect the default" leaves the
    agent to hunt or to quote the number anyway; naming the file collapses the follow-up to one
    grep. So when the header is known this says where to look, and when it is not, it says the
    default is not recorded rather than implying the stated list is one.

    @brief Explain what the configured macro list is and is not evidence of.
    @return The sentence, or "" when nothing was recorded.
    @version 3
    """
    if not macros and not source:
        return ""
    ## THE LEAD SENTENCE IS CONDITIONAL, because a blanket "never a statement about the
    ## repository's default" is FALSE in the one case where the list was read out of the
    ## repository's own header — and a note that contradicts its own next sentence teaches a
    ## reader to skip the whole thing.
    parts = [
        f"`configured_macros` is the variant THIS INDEX was built in (source: {source or 'unrecorded'})."
        if source == "config_header"
        else f"`configured_macros` is the variant THIS INDEX was built in "
        f"(source: {source or 'unrecorded'}), not a statement about what the repository "
        "enables by default."
    ]
    ## THREE SOURCES, THREE DIFFERENT SENTENCES, and the MIXED one is the trap. An earlier
    ## version said "these were STATED BY THE OPERATOR" whenever a statement was involved,
    ## which on mbedtls describes 2 macros out of 144 — the other 142 are read from the
    ## repository's own header. That inverts the disclosure in the opposite direction: it
    ## invites a reader to discount the whole list as an artifact of the build. A correction
    ## that is wrong the other way is not a correction.
    ## THE OVERRIDE CASE, AND IT IS THE ACCEPTANCE BUILD'S CASE. `source` is `flag` whenever a
    ## macro list was passed as an argument — which `clew/cli.py` does with a declared
    ## `predefined:` — so this is the branch mbedtls actually takes. When the declaration ALSO
    ## named a config header, the split is computable and this states the answer rather than
    ## warning that an answer exists. Before, this branch could only ever disclaim.
    if source in ("flag", "declared") and stated_only:
        listed = stated_only if isinstance(stated_only, str) else ", ".join(stated_only)
        parts.append(
            f"These macros were STATED FOR THIS BUILD, so they are evidence about the build and "
            f"not about the repository. AND THE REPOSITORY'S OWN HEADER DOES NOT DEFINE: {listed} "
            f"— those ship OFF and are ON here only because this build declared them. Every other "
            f"macro in the list was read from that header and IS on by default."
        )
    elif source in ("flag", "declared"):
        parts.append(
            "These macros were STATED BY THE OPERATOR for this build — typically so the "
            "preprocessor could reach code behind an `#if` — so they are evidence about the "
            "build and NOT about the repository. A macro listed here may well be OFF, or "
            "commented out, in the repository's own configuration."
        )
    elif source == "declared+config_header" and stated_only:
        ## THE SPLIT IS NOW RECORDED, so this states the answer instead of routing to a file read.
        ## `preprocessor.stated_only` holds exactly the names the operator supplied that the
        ## repository's own header does NOT define — which is to say, the ones that ship OFF. Every
        ## other macro in the list was READ OUT OF that header and therefore ships ON.
        ##
        ## This is the difference between a caveat and an answer. The previous wording said the
        ## field "does not say which came from which" and pointed at the config file; two graded
        ## marks asked which, and the agent went to the shell. Naming the set costs a clause.
        ## ALREADY JOINED, so do NOT join it again. `PreprocessorConfig.as_meta` writes this row as
        ## `", ".join(self.stated_only)` (clew/preprocessor.py:404), so what arrives is a string.
        ## `', '.join()` over a string iterates CHARACTERS, and the one sentence that answers the
        ## question rendered as "M, B, E, D, T, L, S, _, T, H, R, E, A, D, I, N, G, _, C, ,, …".
        ## Normalised rather than assumed: a caller holding the tuple form gets the same output
        ## instead of "('A', 'B')".
        listed = stated_only if isinstance(stated_only, str) else ", ".join(stated_only)
        parts.append(
            f"This list COMBINES the repository's own configuration header with macros stated for "
            f"this build. THE STATED ONES ARE: {listed} — these are OFF in the "
            f"repository's own configuration and are ON here only because this build declared "
            f"them. Every OTHER macro in the list was read from that header and IS on by default."
        )
    elif source == "declared+config_header":
        parts.append(
            "This list COMBINES the repository's own configuration header with macros stated "
            "for this build, and this build did not record which came from which. So a macro "
            "listed here is not evidence that the repository enables it."
        )
    elif source == "config_header":
        parts.append(
            "This configuration was read from the repository's own header, so it does describe "
            "what the repository builds by default."
        )
    if header:
        parts.append(
            f"The repository's own default is in `{header}`: a macro absent or commented out "
            "there is off by default. Read that file to settle what a DEFAULT build does."
        )
    else:
        parts.append(
            "No config header is recorded for this target, so the repository's own default is "
            "NOT in this index — declare `preprocessor.config_header` to make it answerable, "
            "and until then treat the default as unknown rather than as the list above."
        )
    return " ".join(parts)


## @brief Every `kconfig.*` / preprocessor row a build stamped, as a mapping.
## @param conn Open connection.
## @return Unprefixed kconfig keys plus the raw preprocessor macro list, source and header.
## @version 3
## @dg_internal
def _meta(conn: sqlite3.Connection) -> dict[str, str]:
    """Degrades to {} when `build_meta` is absent, matching the query layer's standing
    contract: it returns empty results on a partial database rather than raising,
    because a stale index missing a later layer is a normal thing to query.

    @brief Read the kconfig and preprocessor build_meta rows.
    @return Key -> value, kconfig keys with the prefix stripped.
    @version 3
    """
    if not table_exists(conn, "build_meta"):
        return {}
    rows = conn.execute("SELECT key, value FROM build_meta").fetchall()
    meta = {k[len(_META_PREFIX) :]: v for k, v in rows if str(k).startswith(_META_PREFIX)}
    ## EVERY PREPROCESSOR KEY A CONSUMER READS, and `_PREPROCESSOR_STATED_ONLY` is here because it
    ## was NOT. It was defined, documented, and passed to `macros_meaning` at the call site — but
    ## never fetched, so it resolved to "" on every build and the answer branch that reads it was
    ## unreachable code. The reply fell through to "this build did not record which came from
    ## which" while the split was sitting in `build_meta`.
    ##
    ## The suite could not see it: the existing test calls `macros_meaning` DIRECTLY and never
    ## through `kconfig_space`, so it pinned the wording of a branch nothing could reach.
    for key in (
        _PREPROCESSOR_MACROS,
        _PREPROCESSOR_SOURCE,
        _PREPROCESSOR_HEADER,
        _PREPROCESSOR_STATED_ONLY,
    ):
        meta[key] = next((v for k, v in rows if k == key), "")
    return meta


## @brief The symbol rows, each with the group it belongs to and its gate count.
## @param conn Open connection.
## @return Symbol entries in declaration order.
## @version 1
## @dg_internal
def _symbols(conn: sqlite3.Connection) -> tuple[KconfigEntry, ...]:
    """Joins the choice group in as its HUMAN identity — the prompt, falling back to
    the name — rather than exposing the synthetic `choice_key`. The key is a per-build
    ordinal with no meaning outside the row it joins, so surfacing it would publish an
    implementation detail a consumer could mistake for a stable id.

    `gate_count` is a correlated COUNT rather than a second query, so a symbol that
    gates nothing arrives as 0 rather than as an absence a caller has to interpret.
    Counted only when `kconfig_gates` EXISTS: the two layers fail independently, and
    reporting 0 for every symbol when the gate harvest never ran would be a
    measurement where there is none.

    @brief Read kconfig_symbols with group identity and gate counts.
    @return Symbol entries.
    @version 1
    """
    have_gates = table_exists(conn, "kconfig_gates")
    gates = "(SELECT COUNT(*) FROM kconfig_gates g WHERE g.symbol = s.name)" if have_gates else "0"
    rows = conn.execute(
        "SELECT s.name, s.type, s.prompt, s.help, s.default_expr, "
        "COALESCE(NULLIF(c.prompt, ''), NULLIF(c.name, '')), s.file_path, s.line, "
        f"{gates} FROM kconfig_symbols s "
        "LEFT JOIN kconfig_choices c ON c.key = s.choice_key "
        "ORDER BY s.file_path, s.line"
    ).fetchall()
    return tuple(KconfigEntry(*row) for row in rows)


## @brief The SELECT list that builds a KconfigGate positionally.
## @param conn Open connection to the index.
## @return Comma-joined column expressions.
## @version 1
## @dg_internal
def _gate_columns(conn: sqlite3.Connection) -> str:
    """EVERY OPTIONAL COLUMN IS SELECTED AS A LITERAL WHEN ABSENT rather than omitted, because
    `KconfigGate(*row)` is positional: omitting `origin` on an older index would shift `end_line`
    into its slot and report a line number as a provenance string. The literals equal the
    dataclass defaults, so a degraded database reads back as exactly what it knew.

    ONE CONSTRUCTION SITE for two readers. `gates_covering` needs the same list with a different
    WHERE clause, and two copies of a positional SELECT is how the shift above eventually happens
    for real.

    @brief Build the gate SELECT list for this index's actual columns.
    @return The column expressions.
    @version 1
    """
    selected = ["symbol", "macro", "form", "file_path", "line"]
    selected.append("origin" if has_columns(conn, "kconfig_gates", "origin") else "''")
    selected.append("end_line" if has_columns(conn, "kconfig_gates", "end_line") else "0")
    return ", ".join(selected)


## @brief The gating sites recorded for the whole repo, or for one symbol.
## @param conn Open connection.
## @param symbol Bare Kconfig symbol name (no CONFIG_ prefix) to filter to, or None.
## @return Gate rows in file order.
## @version 3
## @dg_internal
def _gates(conn: sqlite3.Connection, symbol: str | None) -> tuple[KconfigGate, ...]:
    """Accepts the symbol either bare or `CONFIG_`-prefixed, because a caller reading
    a gate out of source code has the prefixed form in front of them and requiring
    them to strip it is a papercut that produces a confident empty result — the
    failure mode gh#31 records for `search`.

    `origin` and `end_line` are selected only when the column is present. An index built before
    gh#390 has no `origin` and one built before the extent work has no `end_line`; `KconfigGate`
    defaults them to `undeclared` and `0`, which is precisely what those indexes knew — reading a
    degraded database thinly rather than failing is the query layer's standing rule.

    @brief Read kconfig_gates, optionally for one symbol.
    @return Gate rows.
    @version 3
    """
    if not table_exists(conn, "kconfig_gates"):
        return ()
    sql = f"SELECT {_gate_columns(conn)} FROM kconfig_gates"  # noqa: S608
    params: tuple[str, ...] = ()
    if symbol:
        sql += " WHERE symbol = ?"
        params = (symbol.removeprefix("CONFIG_"),)
    rows = conn.execute(sql + " ORDER BY file_path, line", params).fetchall()
    return tuple(KconfigGate(*row) for row in rows)


## How many gating SYMBOL NAMES an inventory reply carries before it says it stopped.
##
## MEASURED: mbedtls has 1,107 distinct gating symbols over 12,096 sites. The names are ~27 KB and
## the SITES are 2.1 MB — which is the whole reason this list exists, and why the cap is generous
## rather than tight. A `text` filter usually reduces it to a handful.
_NAME_CAP = 400


## @brief The distinct symbols that gate code, optionally filtered by name.
## @param conn Open connection to the index.
## @param text Substring to filter symbol names by, or None/"" for all of them.
## @return (names, total distinct matching) — names capped at `_NAME_CAP`.
## @version 1
## @req REQ-DDB-QUERY-006
## @dg_internal
def _gate_symbol_names(conn: sqlite3.Connection, text: str | None) -> tuple[tuple[str, ...], int]:
    """WHICH SYMBOLS EXIST, which is the question this corpus says it answers and the one it was
    not answering. `_search_config` asked for the whole space with no symbol, so the reply carried
    every gate SITE: measured on mbedtls 2026-08-14, `search(corpus='config',
    text='MBEDTLS_THREADING_C')` returned 2,149,463 characters — all 12,096 rows, because
    inventory corpora ignore `text` by design — while reporting `found: false` for a symbol whose
    name sits in `configured_macros` in the same reply. In a graded cell that is either a
    budget-destroying reply or a bail-out, on the very axis under test.

    The sites are `dossier`'s job, and were already: `resolve_subject` classifies a gating macro
    as `kind='config'`, and `dossier('MBEDTLS_THREADING_C')` returns its 154 sites correctly
    filtered. So the fix is not a new capability, it is this corpus returning the inventory it
    claims to and routing to the other tool for the detail.

    `text` IS HONOURED HERE, unlike the other inventory corpora. Filtering an inventory by name is
    not ranking, costs one `LIKE`, and is what makes a 1,107-symbol space usable at all — an
    ignored argument that silently returns everything is the shape of the defect above.

    @brief List the distinct gating symbols, filtered and capped.
    @return (capped names, total matching).
    @version 1
    """
    if not table_exists(conn, "kconfig_gates"):
        return (), 0
    sql = "SELECT DISTINCT symbol FROM kconfig_gates"
    params: tuple[str, ...] = ()
    if text:
        sql += " WHERE symbol LIKE ?"
        params = (f"%{text.removeprefix('CONFIG_')}%",)
    rows = [r[0] for r in conn.execute(sql + " ORDER BY symbol", params).fetchall()]
    return tuple(rows[:_NAME_CAP]), len(rows)


## @brief Say what the gate list holds and where the omitted detail is.
## @param names How many symbol names the reply carries.
## @param total How many distinct symbols matched.
## @param filtered True when a `text` filter was applied.
## @return A sentence for the reply, or "" when no gate layer was measured.
## @version 1
## @req REQ-DDB-QUERY-006
def gates_meaning(names: int, total: int, filtered: bool) -> str:
    """AN EMPTY `gates` LIST MUST NOT READ AS "NOTHING GATES CODE HERE". This module exists
    because three different repositories yield zero symbols for three different reasons, and an
    inventory reply that omits the SITES deliberately would reintroduce exactly that ambiguity one
    field over.

    So it says the sites were omitted, why, and the one call that returns them.

    @brief Explain the inventory reply's gate list and route to the sites.
    @return The sentence, or "".
    @version 1
    """
    if not total:
        return ""
    parts = [
        f"{total} distinct symbol(s) gate code in this index"
        + (" matching your text" if filtered else "")
        + ". This corpus lists the symbols that EXIST; the per-site rows are omitted "
        "DELIBERATELY, not absent — mbedtls has 12,096 of them and returning the set costs "
        "over 2 MB."
    ]
    if names < total:
        ## NEVER a silent cap: a truncated inventory that does not say so reads as the whole space.
        parts.append(
            f"Only the first {names} names are listed — pass `text` to narrow, because the "
            f"remaining {total - names} are not shown."
        )
    parts.append(
        "For ONE symbol's gating sites, with their files, lines and branch form, call "
        "`dossier` on the symbol name: it resolves a gating macro as `kind='config'` and "
        "returns those rows filtered."
    )
    return " ".join(parts)


## @brief What the GATE HARVEST measured, independently of whether a Kconfig exists.
## @param conn Open connection to the index.
## @return (`layer_state` value, distinct gating symbols seen).
## @version 1
## @req REQ-DDB-QUERY-006
def _gate_layer_state(conn: sqlite3.Connection) -> tuple[str, int]:
    """gh#404 — BECAUSE `found` ANSWERS A DIFFERENT QUESTION THAN THE ONE CALLERS ASK. `found` is
    true when a Kconfig was discovered and parsed, and that is all it ever claimed. But a caller
    reads `found: false` as "this repository has no configuration space", and on mbedtls — where
    `found` is false, because mbedtls has no Kconfig — the index holds 12,096 gating sites over
    1,107 distinct symbols, harvested from `#if` directives. Kconfig is a Zephyr/Linux convention;
    a header of `#define`s is the dominant C one.

    THREE STATES IN `layer_state`'s EXISTING VOCABULARY, not a fourth spelling of the same idea:
    `absent` when the table was never built (the layer did not run), `empty` when it ran and found
    no gating site, `populated` otherwise. The distinction between the first two is the one this
    project keeps relearning — a table that exists and holds nothing is a MEASUREMENT, while an
    absent table is a detector that never looked, and only the first is evidence about the repo.

    @brief Report the gate layer's state and symbol count.
    @return (state, distinct symbol count).
    @version 1
    """
    if not table_exists(conn, "kconfig_gates"):
        return LAYER_STATE_ABSENT, 0
    count = int(conn.execute("SELECT COUNT(DISTINCT symbol) FROM kconfig_gates").fetchone()[0])
    return (LAYER_STATE_POPULATED if count else LAYER_STATE_EMPTY), count


## @brief A repo's configuration space: its symbols, their groups, and what they gate.
## @param db Index path or open connection.
## @param symbol Restrict the gate list to one symbol (bare or CONFIG_-prefixed), or None.
## @return The space, carrying `found`/`source`/`error` so an empty reply says why, and the
##         configured macros with their provenance and a route to the repo's own default.
## @version 4
## @req REQ-DDB-QUERY-006
def kconfig_space(
    db: DbSource, symbol: str | None = None, include_gates: bool = True
) -> KconfigSpace:
    """`found` comes from `build_meta`, NOT from the presence of the table, and the
    difference is the point. A build that found a Kconfig and failed to parse it
    creates the tables empty and stamps `kconfig.error`; a build on a repo with no
    Kconfig creates nothing and stamps nothing. Deciding `found` from the table would
    collapse those two into one answer, which is precisely the collapse this layer
    exists to prevent.

    The gate list is NOT filtered to declared symbols. A gate on a symbol no Kconfig
    declares is dead code behind a symbol nobody can set — a finding worth returning
    rather than tidying away.

    @brief Query the configuration space with the provenance of the answer.
    @return The space.
    @version 4
    """
    with connect(db) as conn:
        meta = _meta(conn)
        symbols = _symbols(conn) if table_exists(conn, "kconfig_symbols") else ()
        gate_state, gate_symbols = _gate_layer_state(conn)
        ## THE INVENTORY FORM omits the per-site rows and lists the symbol NAMES instead. When a
        ## caller names a symbol the sites ARE the answer, so `include_gates` stays True there;
        ## `_search_config` — which names none — is what was returning all 12,096.
        names, name_total = ((), 0) if include_gates else _gate_symbol_names(conn, symbol)
        return KconfigSpace(
            found=bool(meta.get("source")),
            source=meta.get("source", ""),
            root=meta.get("root", ""),
            symbols=symbols,
            gates=_gates(conn, symbol) if include_gates else (),
            error=meta.get("error", ""),
            configured_macros=meta.get(_PREPROCESSOR_MACROS, ""),
            configured_macros_source=meta.get(_PREPROCESSOR_SOURCE, ""),
            config_header=meta.get(_PREPROCESSOR_HEADER, ""),
            macros_meaning=macros_meaning(
                meta.get(_PREPROCESSOR_MACROS, ""),
                meta.get(_PREPROCESSOR_SOURCE, ""),
                meta.get(_PREPROCESSOR_HEADER, ""),
                meta.get(_PREPROCESSOR_STATED_ONLY, ""),
            ),
            gate_state=gate_state,
            gate_symbols=gate_symbols,
            gate_symbol_names=names,
            gates_meaning=gates_meaning(len(names), name_total, bool(symbol))
            if not include_gates
            else "",
        )


## @brief The configuration gates whose branch covers one source line.
## @param conn Open connection to the index.
## @param file_path Repo-relative path of the file the line is in.
## @param line The line to test for coverage.
## @return (covering gates, number of rows skipped for having no recorded extent).
## @version 1
## @req REQ-DDB-QUERY-006
def gates_covering(
    conn: sqlite3.Connection, file_path: str, line: int
) -> tuple[tuple[KconfigGate, ...], int]:
    """THE INVERSE DIRECTION, AND THE ONE A QUESTION ACTUALLY ASKS. `kconfig_space` answers
    "which lines does symbol X gate", which needs the symbol first. Both graded questions on
    this project's matrix ask the other way round: here is a function — is it compiled in, and
    under what flag. Answering that from the symbol direction means enumerating the whole
    configuration space and reading it, which is an inventory where an adjacency was wanted.

    A ROW WITH NO EXTENT IS SKIPPED AND COUNTED, never guessed at. An index built before the
    extent column stores `end_line = 0`, and both available guesses are wrong in a way that
    looks right: treating it as covering nothing silently reports an entirely gated file as
    ungated, and treating it as covering the rest of the file attributes ordinary code to the
    last conditional above it. So the count comes back with the answer and the caller says
    "this index cannot tell" rather than answering from a coin flip.

    NO POLARITY IS EVALUATED HERE. Each gate carries its own `form`, and the harvest already
    split an `#else` into its own row with the polarity inverted, so a covering set of
    `[ifdef MBEDTLS_THREADING_C]` and one of `[ifndef MBEDTLS_THREADING_C]` are different
    answers about the same symbol. Collapsing them to "gated by MBEDTLS_THREADING_C" would
    throw away exactly the half that says whether the code is there.

    @brief Which gates decide whether one line exists.
    @return The covering gates and the unknown-extent count.
    @version 1
    """
    if not table_exists(conn, "kconfig_gates"):
        return (), 0
    unknown = 0
    if has_columns(conn, "kconfig_gates", "end_line"):
        unknown = int(
            conn.execute(
                "SELECT COUNT(*) FROM kconfig_gates WHERE file_path = ? AND end_line = 0",
                (file_path,),
            ).fetchone()[0]
        )
    else:
        unknown = int(
            conn.execute(
                "SELECT COUNT(*) FROM kconfig_gates WHERE file_path = ?", (file_path,)
            ).fetchone()[0]
        )
        return (), unknown
    ## FILTERED IN SQL, not in Python over every gate in the repository. mbedtls harvests
    ## thousands of gating sites and this runs per dossier subject; reading them all to keep three
    ## would put the cost of the whole configuration space behind one function lookup.
    rows = conn.execute(
        f"SELECT {_gate_columns(conn)} FROM kconfig_gates "  # noqa: S608
        "WHERE file_path = ? AND end_line > 0 AND line <= ? AND end_line >= ? "
        "ORDER BY line",
        (file_path, line, line),
    ).fetchall()
    return tuple(KconfigGate(*row) for row in rows), unknown
