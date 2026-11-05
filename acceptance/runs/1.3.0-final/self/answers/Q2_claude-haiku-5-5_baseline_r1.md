The reply separates the two cases by grading the empty answer and by stamping what the build failed to index. The confidence each one earns depends on which mechanism produced the empty set.

**Layer 1: grading the empty search (`clew/mcp_server/emptiness.py`)**

Every empty `search` gets a note and a `scope` block. The note's wording depends on what was actually checked:

| Empty because | Reply says | Entitled confidence |
|---|---|---|
| Single token, no hits in any corpus, file docs present | "definitive… do not retry" (`_DEFINITIVE`) | Strong, but only for the corpora `search` reads: names and `@brief`, macros, class/struct/union, gating config symbols, file docs |
| Single token, but the index holds matching rows in a corpus `search` doesn't read | "NOT DEFINITIVE", with the rows named and counted (`_UNREAD_CORPUS`) | None for the negative. The name exists; ask `dossier` for it |
| Multi-token conjunction | Names the tokens with zero hits and says to retry without them (`_conjunction_note`) | Explicitly not definitive |
| Prose corpus miss, token present in symbol corpora | "DOES use these terms… not in prose this corpus reads" | Not definitive |
| No file-docs or markdown corpus built | "NOT definitive… rebuild" | Not definitive: an index that cannot look must not report a negative |

The module's own rule is that "nothing matched" is only a negative once the code has checked the other corpora and found nothing there.

**Layer 2: what the build did and didn't walk (`clew/cli.py` `_not_indexed_scope`)**

At build time, the build compares the scanned file set against `path` rows and stamps `not_indexed` (e.g. `.sh=3, .yml=1`) and `not_indexed_count`. This is the "I did not look here" signal. The reply also carries `scope` (source tier such as whole-repo or declared, file count, extensions, top levels) with the long `reason` paragraph stripped.

Presence is the signal. If `not_indexed_count` is zero, both keys are dropped, not emitted as `[]`. An absent key means "not recorded", either because the index predates this report or because nothing walked the tree (e.g. a rustdoc-only build). It never means "nothing missed". The `scope` block is always present on empty replies (when the index has scope rows), so the caller can check whether a miss could be a scope miss at all.

**How much to trust each answer**

- **"Definitive" from a single token** is the strongest claim. It means the token is absent from the searched corpora and not held in any unread corpus. It does not tell you the file type was read. Check `not_indexed` before trusting it for a shell script, YAML, or any file type outside the symbol grammars.
- **`not_indexed` present** means specific file types had no rows in this build. Read those files directly.
- **`not_indexed` absent** tells you nothing about coverage. Don't read it as a clean bill.
- **`not_indexed` is a build-time snapshot.** Its own docstring says the working copy at query time can differ from the walked tree, so after edits it can be stale.

**Gap I did not verify**

`_not_indexed_scope` treats a file as "indexed" if it has any `type = 1` row in `path`. If a scanned file gets a `path` row even when no grammar produced symbols (the test comment describes exactly that case for shell and YAML under the published wheel), it would not appear in `not_indexed`. That would make the report say "covered" for a file whose symbols are absent. Whether `path` rows are written for every scanned file or only for files with symbols needs checking in the build pipeline (`clew/doxygen_splice.py` and the `path` insertion sites) before this report can be relied on for that case.