# SPDX-License-Identifier: MIT
"""What an EMPTY answer says, and how much confidence it is entitled to.

gh#21 and gh#31. Every list-returning tool used to attach one sentence to an
empty result, regardless of why it was empty:

    This is a definitive empty result from the database, NOT an error and NOT a
    malformed call — the database records none. Do not retry this query or fall
    back to guessing.

That wording is CORRECT and valuable for a genuinely absent symbol: an agent
that retries a well-formed query or falls back to guessing wastes a turn and
may fabricate. The defect was never confidence — it was UNIFORM confidence.
The same sentence was attached when:

  * `list_files("*.c")` came back empty in a checkout holding 53 `.c` files,
    which were simply outside the derived index scope. Every clause was true of
    the database and the effect was a false statement about the repository, in a
    sentence engineered to prevent the one check that would refute it. THAT TOOL
    AND ITS GRADER ARE DELETED (see the note where they were); the case is kept
    here because it is half of why this module exists.
  * `search("roots target resolution")` came back empty because the match is a
    CONJUNCTION and `resolution` appears nowhere, while `_target_from_roots` was
    indexed and `dossier` answered on it correctly. Dropping a token is not
    guessing; it is the one correct next move, and the note forbade it.

So this module grades an empty result, and only the first case keeps the strong
wording. Case 2 was `list_files`-only and is gone with it; the grading below is
`search`'s:

  1. **Definitive for the scope** — a single token matched nothing in any corpus.
     Retrying will not help. Say so as forcefully as before.
  2. **Definitive, with a REASON that is not absence** — the pattern's extension
     appears in no indexed file at all. Certain about the index AND certain about
     why, which makes "widen the scope" the next move instead of "give up".
  3. **Not definitive** — an over-specified conjunction, or a corpus this index
     does not carry. Name the token that emptied it and say what to retry.

gh#393 ASKED FOR A FOURTH CASE AND THE ANSWER WAS NO — recorded because the
reasoning is not obvious and was only settled by building it. The complaint was
real: `search("MBEDTLS_THREADING_PTHREAD")` returned a case-1 "definitive" reply
nine times in one benchmark run about a symbol its repository gates 6 lines on. But
the cause was UPSTREAM — the gate harvest was Kconfig-only (gh#390) — and once the
harvest was fixed the query returns rows and never reaches this module at all.

Adding "no gate layer → not definitive" on top of that fix broke
`test_an_absent_symbol_keeps_the_definitive_note`, which names itself the control on
this whole module and warns that weakening it turns the grading into a blanket
hedge. Most indexes lacking that layer lack it because a hand-built fixture never
made one, so the downgrade would have hedged nearly every reply. A genuinely absent
layer is reported by `graph_stats.layer_states` as `absent` rather than `empty`; the
distinction exists in the surface built to carry it and does not belong in every
empty search reply.

**The general rule this leaves behind: fix the corpus, not the sentence about the
corpus.** A wording change that compensates for missing data hedges every honest
answer to excuse one dishonest one.

Every case carries the SCOPE, because "what did you look at" is the question an
empty answer provokes and `status` was the only place that answered it — a
separate call the caller had no reason to make.

WHAT IT CARRIES IS THE COVERED SHAPE, NOT THE DERIVATION. Measured on the mbedtls
acceptance cell: 7 of 21 tool calls returned zero rows and cost 25.5% of every byte
the index arm returned, and a single zero-row `search` cost **2,556 bytes** — larger
than any function body in the run. Two thirds of that one reply was the whole-repo
tier's `scope.reason`, a ~840-byte paragraph emitted TWICE (once as prose, once in the
payload) and ending in "Declare `x-clew: index_scope:` …" — operator
configuration advice an agent cannot act on mid-session, delivered three times in one
cell. The derivation is `status.scope.reason`'s job and is unchanged there; an empty
ANSWER gets the file count, the top levels and the extensions, which are the fields
that distinguish "outside the scope" from "not in the repo".

THE GRADING IS UNTOUCHED BY THAT. What was wrong was VOLUME, not confidence, and the
opposite mistake — dropping the grade to save bytes — is the one `test_emptiness.py`
exists to catch.

@brief Grade an empty query result and word it to the confidence it has earned.
@version 3
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import query as q
from .. import wire

## What `search` reads and what it deliberately does not, one clause each. Stating it is
## half the fix for gh#10: an empty search that does not say which corpora it covered
## cannot be told apart from an empty search that covered everything. Pointing at
## `search_prose` rather than silently falling back to it keeps `search` one tool with one
## meaning — see `query.symbols.search` for why the fallback was rejected.
##
## ONE CONSTANT, SHORTENED, because it was two spending 276 bytes to name two corpora on a
## reply that has already returned nothing. The parenthetical examples ("module docstrings
## and @file comments", "READMEs, design docs") name no corpus a caller can address; the
## load-bearing clauses are WHICH corpora were read and WHERE the unread one lives.
## THE CORPUS LIST IS DERIVED, NOT TYPED. It was typed, and it was WRONG: it named
## "function names, @brief text, file-level docs" for months after classes (gh#315),
## variables (gh#372) and macros (gh#373) had been added to the searcher, so a caller
## reading it could not tell a corpus that had been read and found nothing from one that
## was never read at all — which is the precise distinction the whole module exists to
## draw. Building the sentence from `q.SEARCHED_MEMBERDEF_KINDS` means the next corpus
## appears in the wording the moment it appears in the search, with no edit here.
_SEARCHED = (
    "Searched: names + @brief of "
    + ", ".join(kind for kind, _tier in q.SEARCHED_MEMBERDEF_KINDS)
    + "; macro expansions; class/struct/union; the configuration symbols this repo gates "
    "code on; file docs. NOT searched: markdown or Kconfig prose — that is "
    "search(corpus='prose'), where a conceptual phrase often lands."
)

## Said when the index predates the file-level documentation corpus. An absent corpus
## is not an absent answer, and an index that cannot look must not report a negative.
_NO_FILE_DOCS = (
    "This index carries NO file-level documentation corpus, so a conceptual query had "
    "nowhere to match: NOT definitive. Rebuild with index(action='refresh'), or use "
    "search(corpus='prose')."
)

## NO SECOND ABSENT-CORPUS DOWNGRADE. A `_NO_GATE_LAYER` constant lived here for gh#393 and
## is deliberately gone — see `_verdict` for the control that rejected it. `graph_stats`
## already distinguishes an absent layer from an empty one, which is where that fact belongs.

## The strong wording, kept verbatim for the case that earns it.
_DEFINITIVE = (
    "This IS a definitive empty result from the database, NOT an error and NOT a "
    "malformed call. Do not retry this query or fall back to guessing."
)

## Said when the index HOLDS rows this query would have matched, in a corpus `search`
## does not read. This is the case the strong wording was flatly wrong about four times
## running, and the one it is worded to prevent anybody checking: an agent told "do not
## retry or fall back to guessing" has been told not to make the one call that would
## refute the sentence. So the rows are NAMED and counted, and the reply says where to
## go — a caller who knows a typedef matched can ask for it by name.
_UNREAD_CORPUS = (
    "NOT DEFINITIVE — this index HOLDS matching rows that search does not read: {hits}. "
    "The name exists; search's corpora just do not include that kind. Ask for it by "
    "name with dossier, which returns the row and its body, rather than rephrasing this query."
)

## Said for a graded-down empty result. It keeps the "NOT an error, NOT a malformed
## call" half of the original wording — that half was always true and is what stops a
## caller abandoning the index — and drops only the "definitive" claim it had not earned.
_NOT_DEFINITIVE = (
    "This is NOT an error and NOT a malformed call, and it is NOT a definitive negative either."
)


## @brief One short sentence naming the indexed scope, without its derivation.
## @param scope The summarised scope.
## @return Human-readable scope sentence.
## @version 2
## @dg_internal
def _scope_sentence(scope: q.IndexScope) -> str:
    """THE DERIVATION IS GONE FROM HERE AND ONLY FROM HERE. This used to end with
    "Scope was derived from {source}: {reason}." — and the whole-repo tier's `reason` is a
    ~840-byte paragraph that closes with advice to declare an `index_scope:`. Emitted on
    every empty reply, that is two thirds of a zero-row `search` spent on operator
    configuration a mid-session agent cannot act on. `status.scope.reason` still carries it
    in full, which is the surface an operator actually reads.

    The covered shape rides in the `scope` PAYLOAD rather than being spelled out twice, so
    the extension and top-level lists are named once per reply instead of once in prose and
    once in JSON. The source name stays, because "whole-repo" versus "declared" is one word
    and it is the word that says whether a miss could be a scope miss at all.

    Omitted, not faked, on an index built before the `scope.*` rows existed — an absent key
    honestly reads as "not recorded".

    @brief Render the scope summary as one short sentence.
    @return Scope sentence.
    @version 2
    """
    tier = f", {scope.source}" if scope.source else ""
    return (
        f"Scope: {scope.file_count} indexed file(s){tier} — see the `scope` key for the "
        f"covered shape, or status for how it was derived."
    )


## @brief The scope block for a per-query reply: the covered shape, minus the derivation.
## @param scope The summarised scope.
## @return Wire dict for the scope, with `reason` removed.
## @version 1
## @dg_internal
def _scope_payload(scope: q.IndexScope) -> dict[str, Any]:
    """`reason` is dropped HERE rather than in `wire` or in `IndexScope`, because it is not
    absent — it is expensive, and only on this surface. `status` publishes the same
    dataclass and MUST keep it: an operator asking why a file is missing is exactly who the
    paragraph was written for. A field elided in the serializer would have taken it from
    both.

    Popped rather than rebuilt key by key so a field added to `IndexScope` later reaches
    this reply by default. The costly key is the one named; the cheap ones are not a list
    that can go stale.

    @brief Serialize the scope without its derivation paragraph.
    @return Scope wire dict.
    @version 1
    """
    block = wire.one(scope) or {}
    block.pop("reason", None)
    return block


## @brief Render per-token hit counts as `token=count` prose.
## @param counts Token to independent-hit-count mapping.
## @return Comma-joined rendering.
## @version 1
## @dg_internal
def _render_counts(counts: dict[str, int]) -> str:
    """@brief Render the per-token diagnosis.
    @return Comma-joined `token=count` text.
    @version 1
    """
    return ", ".join(f"{token}={count}" for token, count in counts.items())


## @brief Note for a zero-result multi-token search, naming what emptied it.
## @param text The caller's query.
## @param counts Per-token independent hit counts.
## @return The note text.
## @version 3
## @dg_internal
def _conjunction_note(text: str, counts: dict[str, int]) -> str:
    """gh#31's actual finding: ranking behaved exactly as documented and the NOTE
    was wrong. A token with zero independent hits is the single cause of the
    emptiness, and naming it converts a wasted call into an answer.

    When every token matches something on its own the diagnosis is different in
    kind — no ONE unit carries them all — and the advice is fewer tokens rather
    than a named deletion.

    @brief Word an over-specified-conjunction empty result.
    @return Note text.
    @version 3
    """
    dead = [token for token, count in counts.items() if count == 0]
    if dead:
        blame = (
            f"Token(s) {', '.join(repr(t) for t in dead)} match nothing alone, so they "
            f"alone empty it. RETRY WITHOUT THEM — that is the correct next move, not "
            f"guessing."
        )
    else:
        blame = (
            "Every token matches alone but no one symbol or file carries all of them. "
            "RETRY WITH FEWER TOKENS — the two most distinctive — or use "
            "search(corpus='prose'), which ranks rather than requiring all."
        )
    return (
        f"No matching symbols for {text!r}. {_NOT_DEFINITIVE} Matching is a CONJUNCTION: "
        f"every token must appear in one searchable unit. Per-token hits: "
        f"{_render_counts(counts)}. {blame} {_SEARCHED}"
    )


## @brief Note and payload for an empty `search`.
## @param db Path to the active database.
## @param text The caller's query.
## @return (note text, extra envelope keys) for the empty envelope.
## @version 3
## @req REQ-DDB-QUERY-007
def search_emptiness(db: Path, text: str) -> tuple[str, dict[str, Any]]:
    """Grades the three cases in this module's docstring. The per-token diagnosis
    is computed ONLY here — that is, only once the result is already zero — and only
    for the first `MAX_DIAGNOSED_TOKENS` tokens.

    THE COST DECISION, stated because it was a real choice: one `COUNT` per token,
    paid exclusively on a call that has otherwise returned nothing at all. The
    alternative — diagnosing every search — would tax the common path to serve the
    rare one, and the alternative of never diagnosing is the defect. A cap keeps the
    worst case bounded by the tool rather than by the length of whatever sentence a
    caller pasted in.

    gh#374 adds the second diagnosis, and it is the one that changes what the reply
    CLAIMS: `q.unsearched_corpora` reports rows this query would have matched in a
    corpus `search` does not read, derived by subtracting the searched kinds from the
    kinds this database actually holds. Any hit downgrades the verdict and is published
    as `unsearched_corpus_hits`, so the claim is checkable rather than merely worded.
    Same cost argument, and it is two statements whatever the token count.

    @brief Word and instrument an empty search result.
    @return (note, extra payload).
    @version 3
    """
    tokens = [t.lower() for t in text.split() if t]
    scope = q.index_scope(db)
    extra: dict[str, Any] = {"scope": _scope_payload(scope)}
    unread = q.unsearched_corpora(db, tokens[: q.MAX_DIAGNOSED_TOKENS])
    if unread:
        extra["unsearched_corpus_hits"] = unread
    if len(tokens) > 1:
        counts = q.token_hit_counts(db, tokens[: q.MAX_DIAGNOSED_TOKENS])
        extra["token_hits"] = counts
        note = f"{_conjunction_note(text, counts)} {_scope_sentence(scope)}"
        return (f"{note} {_unread_note(unread)}".rstrip(), extra)
    verdict = _verdict(db, unread)
    return (
        f"No matching symbols for {text!r}. {verdict} {_SEARCHED} {_scope_sentence(scope)}",
        extra,
    )


## @brief The sentence naming rows an unread corpus holds, or '' when there are none.
## @param unread Mapping of unread corpus name to matching-name count.
## @return Sentence text, empty when nothing matched outside the searched corpora.
## @version 1
## @dg_internal
def _unread_note(unread: dict[str, int]) -> str:
    """@brief Word the unread-corpus finding.
    @return Sentence, or ''.
    @version 1
    """
    if not unread:
        return ""
    hits = ", ".join(f"{count} {kind}" for kind, count in unread.items())
    return _UNREAD_CORPUS.format(hits=hits)


## @brief Grade a single-token empty search: definitive only when nothing unread matched.
## @param db Path to the active database.
## @param unread Mapping of unread corpus name to matching-name count.
## @return The verdict sentence for the note.
## @version 2
## @dg_internal
def _verdict(db: Path, unread: dict[str, int]) -> str:
    """THE STRONG WORDING IS NOW EARNED PER CALL rather than attached to a shape. A
    single token that matched nothing used to be treated as proof of absence, which
    confuses "nothing exists" with "I did not look there" — and this project keeps
    finding that the second one was true. `q.unsearched_corpora` asks the database
    which corpora `search` did not read and whether any of them holds this query, so
    "definitive" is asserted only after that question comes back empty.

    The ORDER of the downgrades matters, and it runs most-specific first. A matching row in
    an unread corpus is a statement about THIS query and outranks everything below, which
    are statements about the index as a whole: if a typedef matched, saying "rebuild to get
    file docs" would send the caller to fix the wrong thing.

    EXACTLY ONE ABSENT-CORPUS DOWNGRADE, and that is deliberate. gh#393 proposed a second
    one for the preprocessor-gate layer and it was BUILT AND REVERTED, because
    `test_an_absent_symbol_keeps_the_definitive_note` failed — the test that calls itself
    "THE CONTROL ON THE WHOLE CHANGE" and says that if it ever needs weakening, the fix has
    become a blanket hedge. It was right: most indexes that lack the gate layer lack it
    because a hand-built fixture never made one, so downgrading on absence would hedge
    almost every reply and spend the strong wording that gh#31 fought to earn.

    THE REAL DEFECT WAS UPSTREAM ANYWAY. `search("MBEDTLS_THREADING_PTHREAD")` returned a
    confident empty result nine times in one benchmark run because the HARVEST was
    Kconfig-only; gh#390 fixed that and the query now returns rows, so it never reaches
    here. A layer that is genuinely absent is reported by `graph_stats.layer_states` as
    `absent` rather than `empty` — the distinction already exists, in the surface built to
    carry it, and repeating it in every empty search reply buys nothing.

    @brief Pick the earned verdict for a single-token empty result.
    @return Verdict sentence.
    @version 2
    """
    if unread:
        return _unread_note(unread)
    return _DEFINITIVE if q.has_file_docs(db) else _NO_FILE_DOCS


## `list_files_emptiness` and its `_files_note` LIVED HERE and are DELETED with the
## `list_files` tool. They were the second and only other caller of `_scope_sentence` /
## `_scope_payload`, and grading the three `*.c` cases — no such extension anywhere, the
## extension is indexed but the glob missed, nothing indexed at all — was the case gh#21
## opened with. Keeping the grader with no tool able to reach it would have left a
## reply-wording claim that nothing can be tested against a real reply, which is the
## `preflight_mcp` shape: a check whose promise and whose code had drifted apart and which
## nobody could run to find out. `_NOT_DEFINITIVE` STAYS — `search` reaches it through
## `_conjunction_note`, so it is not orphaned by this deletion.
##
## What is LOST and where the fact now lives: the per-file inventory itself is gone from
## the MCP surface, so "is this file indexed" is answered by `status`/`graph_stats`, which
## publish the derived scope (source, reason, extensions, top levels, excludes) and the
## `indexed_files` / `substantive_files` / `barren_files` counts. `graph_stats` also keeps
## the `external_roots` LIST, so the nested-tree fact survives at root granularity. What
## has NO other home is the per-file documented-symbol count — see the deletion report.


## Said when the prose corpora were read and the token IS in this index elsewhere. The prose miss
## is then a fact about WHERE the token is written, not about whether the repo contains it — and
## the strong wording told a reader the opposite, with "do not retry or fall back to guessing"
## attached, which is the sentence that sent a graded cell to grep three times.
_PROSE_ELSEWHERE = (
    "NOT DEFINITIVE — this repository DOES use these terms; they are just not in prose this "
    "corpus reads. Per-token hits across the symbol corpora: {hits}. Ask "
    "search(corpus='symbols') or dossier for the name itself."
)

## Said when the markdown corpus was never built. An index that cannot look must not report a
## negative — the same rule `_NO_FILE_DOCS` states one corpus over.
_NO_PROSE_CORPUS = (
    "This index carries NO ingested markdown corpus, so a documentation query had nowhere to "
    "match: NOT definitive. Rebuild with index(action='refresh') to ingest the repo's docs."
)


## @brief Note and payload for an empty `search(corpus='prose')`.
## @param db Path to the active database.
## @param text The caller's query.
## @return (note text, extra envelope keys) for the empty envelope.
## @version 1
## @req REQ-DDB-QUERY-007
def prose_emptiness(db: Path, text: str) -> tuple[str, dict[str, Any]]:
    """gh#404 — THE PROSE CORPUS INHERITED A CERTAINTY IT NEVER EARNED. `_search_prose` passed no
    `diagnose` callable, so `_many` applied its DEFAULT wording: "a definitive empty result… Do not
    retry this query or fall back to guessing." Measured on mbedtls,
    `search(corpus='prose', 'MBEDTLS_ALLOW_PRIVATE_ACCESS')` answered exactly that about a token
    the same index holds in three `memberdef` rows — and the agent obeyed the instruction and ran
    three greps.

    GRADED BY THE SAME MACHINERY AS THE SYMBOL CORPUS, not a second one. `token_hit_counts` already
    answers "does this index contain this token at all", and reusing it means the two corpora
    cannot disagree about whether a name exists. The repo has been here twice (D1, D1b); what those
    fixes established is that a note claiming certainty must have EARNED it, and the only way to
    earn it here is to have looked elsewhere and found nothing.

    THE ABSENT-CORPUS CASE IS DISTINCT and is checked first, because "we searched documentation and
    it does not say this" and "this index has no documentation" are different facts and the second
    must never be reported as the first.

    @brief Word and instrument an empty prose result.
    @return (note, extra payload).
    @version 1
    """
    tokens = [t.lower() for t in text.split() if t]
    extra: dict[str, Any] = {}
    if not q.has_prose_corpus(db):
        return (f"No prose matches for {text!r}. {_NO_PROSE_CORPUS}", extra)
    counts = q.token_hit_counts(db, tokens[: q.MAX_DIAGNOSED_TOKENS])
    present = {token: n for token, n in counts.items() if n}
    if present:
        extra["token_hits"] = counts
        return (
            f"No prose matches for {text!r}. "
            + _PROSE_ELSEWHERE.format(hits=_render_counts(present)),
            extra,
        )
    ## Nothing anywhere: the corpus was read, the symbol corpora were read, and neither holds the
    ## token. THAT is a definitive negative, and it keeps the strong wording precisely because it
    ## is now the case that earns it.
    if counts:
        extra["token_hits"] = counts
    return (f"No prose matches for {text!r}. {_DEFINITIVE}", extra)
