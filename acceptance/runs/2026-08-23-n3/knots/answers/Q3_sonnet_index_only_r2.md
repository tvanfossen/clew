Now I have the full mechanism. Here's what counts as an edge in knots' import-coupling graph, and what deliberately doesn't:

**What produces an edge**

The graph (`ImportGraph`, `src/coupling.rs`) is built in two phases:

1. **Raw import extraction** comes from outside this module entirely — `lang_parsing_substrate::import_sources`, the same syntactic tree-sitter substrate the rest of knots uses. Each file yields a list of raw import strings (e.g. `use foo::bar;`, `import x from './y'`, `#include "z.h"` — whatever the grammar's import-like nodes are).
2. **Module keying** (`module_key`) reduces every corpus file to its bare file-stem (`Path::file_stem()` — no directory, no extension). `index_module_keys` builds two maps from this: how many files share a given stem (`key_counts`) and which one file "owns" that stem (`key_owner`).
3. **Candidate reduction** (`resolve_candidate`) reduces a raw import string the same way: strip a leading path prefix, strip a trailing extension *if it's one of the languages' known extensions*, then strip a namespace/qualifier separator (`::` or the last `.`) down to the trailing identifier.
4. **Resolution** (`resolve_targets`) accepts a candidate as a real edge only if:
   - the reduced candidate's key count is **exactly 1** (unique across the whole corpus), and
   - the owning file is not the importing file itself (no self-edges).

An edge is a `(file, target_file)` pair, and `ImportGraph.edges: HashMap<String, HashSet<...>>` dedupes automatically — multiple `use` statements pulling from the same target file still count as **one** edge for Ce/Ca purposes (`FileCoupling::ce = targets.len()`).

**What deliberately does not produce an edge**

- **Any import whose reduced stem matches zero or more than one corpus file.** `key_counts.get(&candidate) != 1` is a hard skip — this is a *conservative, no-guessing* rule, not a bug: ambiguous stems (two files both named e.g. `types`) are dropped rather than arbitrarily picked.
- **Self-imports** — `target != path` is checked explicitly.
- **External/third-party imports** — stdlib, crates.io/npm/pip packages, anything not matching a file stem physically present in the analyzed corpus. This is inherent to the resolution being purely stem-based against `key_owner`, which is only ever populated from the files passed in.
- **Directory/package-level imports** — resolution only ever targets a single file (by stem), never a directory or a re-export barrel; a `mod.rs`/`__init__.py`/`index.ts`-style directory import either matches its own stem coincidentally or resolves to nothing.

The file doc for `src/coupling.rs` itself calls this out explicitly: resolution here is "a best-effort heuristic, not real module resolution" — it's a syntactic, filename-stem matching scheme layered on the substrate's raw import strings, not a semantic linker. Anything the heuristic can't pin to exactly one corpus file by trailing identifier is silently excluded from Ce/Ca rather than guessed at.
