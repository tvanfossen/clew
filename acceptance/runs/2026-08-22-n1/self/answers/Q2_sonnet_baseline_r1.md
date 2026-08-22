I now have a full picture of the machinery in `clew/mcp_server/emptiness.py` (grading `search`) plus its `clew/query/corpus.py` and `clew/query/symbols.py` backing. Here's how a zero-row reply distinguishes the two claims, and what confidence rides on each.

## The distinction is structural, not phrased

An empty `search` reply is never handed one fixed sentence. `search_emptiness()` (and `prose_emptiness()`) computes, on the zero-row path only, two extra facts before wording anything:

1. **`q.unsearched_corpora(db, tokens)`** — derived by *subtraction*: the kinds this database actually holds minus the kinds `search` reads. If the token matches rows in a corpus `search` doesn't look at (an enum, a macro, a class — whatever the searcher hasn't been taught yet), that's "I did not look there," and it outranks everything else because it's a fact about *this query*, not the index as a whole.
2. **`q.has_file_docs(db)` / `q.has_prose_corpus(db)`** — whether the corpus even exists in this build. If it was never ingested, an empty result there is "I have no eyes on that corpus at all," not "I looked and it's absent." Same idea for `q.token_hit_counts()` on multi-token queries: a token with zero independent hits anywhere names *itself* as the reason, rather than the whole conjunction being asserted absent.

So "not in the repository" vs. "not where I looked" is answered by literally querying the index's own coverage before the note is written — the module's own framing is "fix the corpus, not the sentence about the corpus," and the wording is just the rendering of that check.

There's a third mechanism at the MCP boundary (`tools_query.py::_withdraw_definitive`): if the reply carries `schema`-axis staleness (built by an older pipeline, possibly missing whole layers), any "definitive"/"do not retry" language already drafted gets rewritten to explicitly say the layer may be *missing rather than empty*, and to route to `index(action='refresh', force=True)`. That's the same distinction applied one level up — a stale index is "I haven't looked with current eyes" — checked once, centrally, so no per-tool verdict has to reason about it.

## Confidence attached to each case

- **Genuinely absent, definitive** (`_DEFINITIVE`): earned only when (a) no unread corpus holds a match, and (b) the relevant corpus was actually built. Wording: "This IS a definitive empty result… Do not retry or fall back to guessing." This is the *only* case that tells the caller to stop.
- **Absent corpus** (`_NO_FILE_DOCS` / `_NO_PROSE_CORPUS`): zero confidence about the repository. "NOT definitive," with the remedy named (`index(action='refresh')` or `search(corpus='prose')`).
- **Unread-corpus hit** (`_UNREAD_CORPUS` / `_PROSE_ELSEWHERE`): zero confidence, and stronger than that — the reply actively contradicts "absent": rows exist, named and counted, with a pointer to `dossier` to fetch them by name.
- **Over-specified conjunction** (`_conjunction_note`): not definitive; names the dead token(s) and says retry without them, or drop to fewer/most-distinctive tokens.
- **Schema-stale withdrawal**: whatever verdict was drafted gets overridden to not-definitive, because a schema-stale index cannot certify an absent layer as absent.

The module is explicit that this is a *four-case-considered-and-rejected* design: gh#393 tried adding a blanket downgrade for "no gate layer" and it was built and reverted, because most such indexes lack the layer only because a hand-built fixture never populated it — downgrading on mere absence would have hedged nearly every reply and diluted the one case that's supposed to carry full weight. Confidence is earned per call from a checked fact, never assigned by corpus shape alone.
