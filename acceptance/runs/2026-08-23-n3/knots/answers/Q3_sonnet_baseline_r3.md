Now I have the full picture, straight from `src/coupling.rs`.

**What counts as an edge**

An edge `file A → file B` is created only when all of the following hold:

1. **A is a raw import string extracted syntactically** by `lang_parsing_substrate::import_sources` (the tree-sitter substrate's per-language import/include extraction) — e.g. a JS `./bar` import, a Java `com.example.util.Helper` import, a `#include "foo.h"`.
2. That raw string reduces, via `resolve_candidate`, to a single trailing identifier: strip any path prefix (up to the last `/` or `\`), strip a trailing extension if it's a *known source extension* (drawn from the same language table that drives `LANGUAGES`/`SUPPORTED_EXTENSIONS`), then strip a namespace separator (`::` or a final `.`).
3. That candidate identifier matches **exactly one** file's `Path::file_stem()` in the analyzed corpus (`index_module_keys`/`key_counts`).
4. The match isn't a self-import (`target != path`).

If all four hold, a directed edge is added to `ImportGraph`, and Ce/Ca/Instability (`ce = |targets|`, `ca` = count of files pointing at this one, `instability = ce/(ce+ca)`, `0.0` when both are zero) are derived purely from this resolved graph. Multiple imports from A to the same B collapse to one edge (`HashSet<String>` targets) — Ce counts *distinct* files, not raw import statement count.

**What deliberately does not count**

- **Any import that doesn't resolve to a corpus file at all** — third-party libraries, stdlib imports, unresolvable dynamic `require()`s. These are explicitly excluded so Ce/Ca measure coupling *within the analyzed corpus only*, matching the classic Robert Martin Ce/Ca/Instability scope. The doc comment is explicit that counting externals would inflate Ce for nearly every file and push Instability toward 1.0 corpus-wide, erasing the signal (see the `external_imports_do_not_create_edges` test: importing `numpy` yields `ce = 0`).
- **Ambiguous stem matches** — if two or more corpus files share the same `file_stem` (e.g. `pkg_a/utils.py` and `pkg_b/utils.py`, or two different-language `mod.rs`/`utils.js` collisions), the candidate resolves to **no edge at all**, for *either* file, rather than picking one arbitrarily. The rationale stated in the source: "a wrong edge is worse than a missing one" (`ambiguous_stem_resolves_to_no_edge` test).
- **Self-imports** — even if a file's import string were to resolve back to itself, `resolve_targets` explicitly filters `target != path`.

So the graph is a best-effort heuristic, not true module resolution — it never does real path/classpath/package resolution, just stem-matching with a fail-closed policy on ambiguity, and it's scoped to intra-corpus dependencies by design, not total fan-out.
