# Provenance cut from the served tool descriptions (2026-08-11)

Not loaded: `load_descriptions` globs `*.json` and skips `_`-prefixed names, so this file
costs nothing on the wire. It exists because a **tool** description file may not carry a
`why` key — `_ALLOWED_KEYS` refuses one — while a `_templates/*.json` file may, and the
template `why` blocks already hold their own cut material. This is the same knowledge for
the tool files, which have nowhere else to put it.

## Why anything was cut

The fixed tool-description surface is re-read on every turn of every session. Measured on
the mbedtls acceptance cell: 14,935 tokens of description, 19.4% of the cell's budget,
paid before any query runs. The 2026-08-11 pass cut the SERVED surface from 47,701 to
24,376 bytes. The rule applied was: keep what a caller needs to CALL the tool correctly
and not misread its output; cut measured history, retracted-claim narrative, and design
rationale addressed to a maintainer.

**Served bytes are not file bytes.** A `_templates` block is charged once per USING tool,
so before the cut the served total (47,701) EXCEEDED the on-disk total (45,390). Shrinking
a shared block is worth its length times its user count; check
`.claude/tmp/desc_bytes.py` before optimising the wrong file.

## Measurements removed from tool description files

- **lock_roster** — the identity-vs-physical distinction was illustrated with "measured on
  a real target, 52 of 97 belonged to a vendored submodule". The mechanism (identity is
  `(name, scope, kind)`; `origin` decomposes `distinct_mutexes`) is retained; the figure is
  here.
- **graph_stats** — `pairs_without_nonfuzzy` carried "its share is routinely large (87.8%
  measured on one C++ target)". The parenthetical is dropped; the warning is retained.
- **neighbours template** — the thread-membership figure (26 of 3,456 functions on a large
  C++ target) moved into that file's own `why` block, along with the `ast_member` fuzziness
  reason and the one-macro-witness-per-pair rule.
- **provenance template** — the mbedtls 2,527/4,206 and entropic 2/2,058 provenance shares
  are in that file's `why` block.

## Deliberate structural changes, not rewording

- **The `status`-first mandate is DELETED.** It read "CALL THIS FIRST in a new session".
  Measured: one such call cost 69,573 first-turn tokens and contributed nothing to the
  answer. Replaced with a conditional — call it when an answer looks wrong, when an
  expected symbol is missing, or when the repository may have moved. Every query reply
  already names the target it answered from, which is what the routine call was for.
- **`source` no longer includes the `provenance` block.** That block's whole job is to stop
  an empty brief being read as "undocumented"; `source` returns lines, not a brief, so the
  trap cannot arise there. Saved 441 bytes.
- **`resolve_symbol` no longer includes `provenance` or `disambiguate`.** It is the tool
  that PRODUCES `candidates`; its own two sentences now say to copy a `qualified` and where
  to pass it. The full block stays on the tools that CONSUME the argument (dossier,
  callers, callees, source). Saved 945 bytes.
- **`build_or_refresh`'s `options` schema was compressed to the key list.** The per-key
  shapes were dropped in favour of naming the general rule (path or inline document) and
  the fact that a wrong shape is refused BY NAME rather than silently defaulted. The
  argument is self-describing on failure, which is the case where prose is redundant.

# Round 2 (2026-08-11): 24,376 -> 11,968 served bytes

## Why a second pass, when round 1 already halved it

The economics changed. At 0.5.0 an acceptance cell ran ~56 turns and the payload dominated;
cells now run 12-15 turns, so the FIXED PROMPT is the dominant per-turn cost. Measured on the
current mbedtls sonnet cells: the index arm makes 13 calls to the source arm's 8, and its cost
per call went UP (31,296 -> 37,040 tokens) while the source arm's HALVED (66,604 -> 40,741).
Payload size is not the lever — index payloads measured 24% SMALLER than the source arm's — so
the two levers are the fixed surface and the turn count. This pass is the first.

## Method

Same rule as round 1, applied harder: a description must let a model CHOOSE the tool and READ
its output correctly, and nothing else. Cut on sight — worked examples, design rationale,
retracted-claim narrative, measured history, argument addressed to a maintainer, and any
sentence that would still be true if deleted. Everything of lasting value moved into a `why`
block (templates) or into this file (tool files, which may not carry a `why` key).

## Template multipliers, before -> after

A `_templates` block is charged once per USING tool, so a byte there costs its user count.

| template | users | before | after | wire saving |
|---|---|---|---|---|
| neighbours | 2 (callers, callees) | 1,403 | 710 | 1,386 |
| disambiguate | 3 (callers, callees, dossier) | 468 | 168 | 900 |
| provenance | 2 (dossier, search) | 425 | 219 | 412 |
| ambiguous | 2 (callers, callees) | 268 | 131 | 274 |
| rows | 4 | 100 | 100 | 0 (already one sentence, and four tests pin it) |

The five shared blocks account for 2,972 of the 12,408 bytes saved — a quarter of the pass, from
1,171 bytes of editing.

## Structural changes, not rewording

- **`build_or_refresh` no longer lists the nine `options` keys.** The list was 130 bytes of
  schema that the failure path already publishes: an unknown key is refused BY NAME and names
  the allowed set, and `propose_declaration` returns a `statement` this argument accepts
  verbatim, so a model rarely has to know the key names in advance. The categories
  (accessor families, thread-spawn wrappers, locks, dispatch, predefined macros) are kept
  because they are what makes a model realise the argument is relevant at all.
- **The `status` prose about `scope.operator_excludes`, `coverage` and `stated_options` is
  gone**; `build_or_refresh` still documents both round trips, which is where an operator is
  when they need them.
- **`kconfig` lost the `symbol` argument note and the search_prose cross-reference**, both
  recoverable from the schema and from search_prose's own description.
- **Cross-tool pointers were cut to one direction.** dossier -> callers/callees stays, because
  it prevents a wasted call; callers/callees -> chain_trace is now three words.

## Measurements and reasoning removed from tool files this round

- **graph_stats** — `calls.rows_by_confidence` and the `symbol_provenance` / `barren_ratio`
  enumeration. `row_meaning` is quotable in the payload itself.
- **lock_roster** — "ordered by acquisition count descending" and "`acquisitions: 0` means
  declared and never taken", both readable from the rows.
- **thread_roster** — the second empty-answer case (an index predating the spawn-site record,
  which forbids quoting a first-party count) and the "pass a row's `entry` to dossier" pointer.
- **chain_trace** — `direction`'s two values (in the schema) and the reason non-fuzzy-only
  traversal exists (a fuzzy edge multiplies one unconfirmed name into a wrong subtree). The
  CONSEQUENCE — a short chain may mean low trust, not a short call path — is kept.
- **dossier** — "there is no separate tool for any of these four: do not look for one" was
  shortened to "so do not read the file", and the virtual-dispatch paragraph to one clause.

## Idea NOT built: lazy long-form descriptions

MCP has no mechanism for a tool to lengthen its own description after first use, and the
registration-time list is what a model reads on every turn. A tool COULD return its long form
inside its first reply's envelope — the payload is paid once per call rather than once per turn
— but that trades a fixed cost for a per-first-call one and only pays when a tool is called at
most once per session. Not built; recorded so the next pass does not re-derive it.

## Known weak assertion, reported not exploited

`test_neighbour_tool_descriptions_match_what_the_tools_now_return` checks `field in desc` for
every neighbour wire field, so `via_macro` is satisfied vacuously by `via_macro_expansion`
containing it. The cut did NOT lean on that hole: the served text names both spellings
literally, as `via_macro`/`via_macro_expansion`. The nearby dossier-panel assertion already
uses a word-boundary regex for exactly this reason; this one has not been converted.
