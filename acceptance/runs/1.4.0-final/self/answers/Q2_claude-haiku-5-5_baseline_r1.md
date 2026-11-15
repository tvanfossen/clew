The reply does not use one sentence for every empty result. `search` grades each empty result against what the index actually covers, and only one case earns the strong "definitive" wording. This is from reading `clew/mcp_server/emptiness.py`, `clew/query/models.py` and `clew/query/corpus.py`. I did not build an index or run a live query.

**Every empty reply carries its scope.** `search_emptiness` and `prose_emptiness` attach a `scope` block: the derivation source (`declared`, `doxygen-guard`, `doxyfile`), the indexed file count, top-level directories and extensions. The derivation paragraph (`reason`) is dropped from this reply to save bytes but stays in `status`. The reply also says which symbol corpora it read and where the unread one lives. A caller can therefore check whether the path it asked about was ever in scope, rather than trusting a bare "no rows".

**The grades:**

| Case | Reply | Confidence |
|---|---|---|
| Single token, matches nothing in any corpus, index has file docs | "definitive… do not retry or fall back to guessing" | Strong, but only about this index's read corpora, not the repository |
| Single token, but rows exist in a corpus `search` does not read (e.g. typedefs) | "NOT DEFINITIVE", names the rows and their count, points to `dossier` | None for the negative; the name exists |
| Multi-token query, each token matched alone | "NOT definitive", retry with fewer tokens | Low; the conjunction emptied it, not absence |
| Multi-token query, one token has zero hits | Names the token, says retry without it | Low, but the next move is concrete |
| Prose search, token present in symbol corpora | "NOT DEFINITIVE — this repository DOES use these terms" | None for prose; the term is in the repo |
| Index has no file-doc or markdown corpus | "NOT definitive", says rebuild | None; the index could not have looked |

**What the scope fields do not settle.** The grades speak to the database, not the checkout. A file outside the derived scope is reported only through the scope fields and `status`. The "not indexed by extension" count (`not_indexed` / `not_indexed_count`) exists in the index metadata, but `search` does not currently print it in the reply. The code says an index built before that stamp reports nothing, not an empty list, so absence of the key means "not recorded", not "nothing missed".

**Confidence in the strong case is a judgment, not a proof.** The code defends the "definitive" wording by checking the unread corpora first. Its stated fallback is that a layer which is truly absent shows up as `absent` in `graph_stats.layer_states` rather than as `empty`. The authors chose not to downgrade every reply on missing layers, because most test fixtures lack them and that would hedge almost every honest answer.

**Short version:** an empty `search` says "definitive" only when a single token matches nothing in any corpus it read, and the index has the corpora needed to have looked. Every other empty reply names what it did not read or what emptied it, and it carries the scope so the caller can tell "outside scope" from "not in the repo".