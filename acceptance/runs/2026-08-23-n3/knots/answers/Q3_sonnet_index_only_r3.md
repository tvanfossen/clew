I now have the full pipeline from raw import string to graph edge. Here's the answer:

## What counts as an edge

An edge is a **file→file** relationship in `ImportGraph.edges: HashMap<file, HashSet<file>>`, built in two phases (`src/coupling.rs`):

1. **Extraction** (`extract_file_imports` → `lang_parsing_substrate::import_sources`): for every file that parses under a compiled-in grammar, pull the raw import/`use`/`include` strings straight out of the syntax tree — a purely syntactic pass, language-neutral like the rest of knots.

2. **Resolution** (`resolve_targets` → `resolve_candidate` + `index_module_keys`):
   - Each raw import string is reduced to a bare identifier: strip any path prefix (up to the last `/` or `\`), strip a trailing extension *only if it's one of the tool's known source extensions*, then strip a namespace separator (`::` for Rust-style, or `.` otherwise) down to the last segment.
   - Every corpus file is separately indexed by its **module key** — just its `file_stem()` (filename minus directory and extension), with a count of how many files share that stem.
   - A candidate import becomes an edge **only if its resolved key matches exactly one corpus file's stem** (`key_counts == 1`). If zero files share that stem, or more than one does, the import is dropped — it counts as neither Ce nor Ca.
   - A self-import (target == path) is explicitly excluded.
   - Each surviving edge is deduplicated into a `HashSet`, so **N imports of the same file only count once** toward Ce.

So an edge = "file A contains at least one import statement whose final identifier segment matches the file-stem of exactly one other file in the analyzed corpus, and that file isn't A itself."

## What deliberately does not count

- **Ambiguous stems.** If two files in the corpus share a filename stem (e.g. `utils.py` and `utils.rs`, or two `mod.rs`/`__init__.py`-style files), imports resolving to that stem are dropped rather than guessed at — the code explicitly rejects `key_counts != 1`.
- **Imports of anything outside the analyzed file set.** Standard-library imports, third-party packages, or any file not included in the current run (e.g. not passed with `--recursive`, or excluded/filtered out) never resolve to a corpus file, so they contribute to neither Ce nor Ca. There is no external-package tracking at all.
- **Self-imports.** `target != path` is enforced.
- **Duplicate imports of the same target within one file.** Collapsed via `HashSet`, so Ce reflects distinct dependencies, not import statement count.
- **Files that fail to parse or read**, or whose language isn't compiled in — silently skipped in `extract_file_imports` (the doc note says this mirrors `collect_all_metrics`'s skip behavior without re-warning, since that pass already warned).
- **Real module/path semantics.** The file doc for `coupling.rs` is explicit that this is "a best-effort heuristic, not real module resolution" — there's no package-manager awareness, no relative-vs-absolute path resolution, no re-export following. It's a filename-stem match, full stop.

One thing the index can't tell me directly: I don't have the body of `lang_parsing_substrate::import_sources` itself (it's an external crate/dependency, not indexed in this repo — confirmed by the earlier "not indexed" result), so I can't say precisely which node kinds per language it treats as an "import" at the syntax level. That's a genuine gap — everything downstream of extraction is fully visible in the index, but the extraction grammar per language would require reading that substrate crate's source directly.
