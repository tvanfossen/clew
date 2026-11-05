The reply separates the two cases with fields, not with the row count. An empty result is never read as a plain "no".

**What the index checks, and what it says when it finds nothing**

- **`target`** names the repository that answered. Every reply carries it, so you can see which index was searched.
- **`not_searched`** names any part of the repository the reply did not read. In a split repository, each vendored dependency has its own index, and a first-party miss says it covered only first-party. The routing tests cover this case: a first-party miss is scoped, and unbuilt parts are listed as not searched.
- **`scope`** on a symbol-corpus miss gives the covered shape: file count, top-level directories, extensions, and `not_indexed` with counts. Files of other types, such as `.rs`, `.toml`, or `.sql`, are listed there as outside the index.
- **A `note` on the symbol corpus** says plainly that the empty result is "NOT a definitive negative." It also reports per-token hits. A multi-token query can come back empty even when each token occurs in the repository, because matching requires every token to appear in one searchable unit. In this case `not_searched=3` and `empty=204` both matched, but no single symbol carried both.

**Which corpus was read decides what the miss means**

- **`symbols`** covers function, variable, macro, type and per-file doc names and their briefs. It does not cover markdown or Kconfig prose, and it does not cover function bodies. A miss there does not rule out a string literal inside a body.
- **`prose`** covers markdown and reStructuredText. It ranks rather than requiring every token, so a conceptual phrase is more likely to land.
- **`code`** covers function bodies, which is where keys, literals and strings are found.
- **Roster corpora** (`locks`, `threads`, `config`, `files`) enumerate a whole layer. A miss there is a real absence within what that layer records. `files` counts only what the index holds, not the whole tree.

**Confidence each answer deserves**

- **"Not in this repository"** holds only when the reply has no `not_searched`, the corpus matches what you are looking for, and no other corpus outside search's reach could hold it. The search tool's own wording claims certainty only in that case.
- **"I did not look where it lives"** is what `not_searched`, a `scope` that excludes its file type, or a corpus mismatch tells you. That is a statement about coverage, not about the code. Treat it as a reason to rerun the query in the right corpus or read the file directly.
- **A symbol miss with a multi-token query** is weak evidence. Retry with the two most distinctive tokens, or use `prose`, before concluding anything.

**Limits of this answer**

I answered from the index only: the search and dossier replies for `search`, the `not_searched` documentation, and the empty-result note. I did not confirm that the reply text for the split-repository case appears exactly as I describe. The phrasing above comes from the routing docs and tests as the index reports them.