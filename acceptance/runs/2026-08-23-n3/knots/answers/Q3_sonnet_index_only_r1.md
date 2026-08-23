I now have the full pipeline. Here's the answer.

## What counts as an edge

An edge `A → B` in knots' import-coupling graph exists when file A's syntactic import list contains a string that resolves, unambiguously, to file B's module key — where "resolves" means:

1. **Extraction** (`extract_file_imports`, `src/main.rs`): each file is parsed and its raw import strings pulled out by the tree-sitter substrate (`lang_parsing_substrate::import_sources`) — this is purely syntactic (whatever the grammar recognizes as an import/use/include statement), not a semantic resolver.
2. **Candidate reduction** (`resolve_candidate`): each raw import string is normalized to a single trailing identifier — strip any path prefix up to the last `/` or `\`, strip a trailing known source-file extension (from `known_source_extensions()`, i.e. any extension any supported language declares), then take whatever follows the last `::` (or, failing that, the last `.`).
3. **Module-key matching** (`module_key` / `index_module_keys`): every corpus file is keyed by its bare file stem (filename minus directory and extension). The reduced import candidate is looked up against this map of stem → file.
4. **Uniqueness gate** (`resolve_targets`): the edge is only added if exactly **one** corpus file shares that module key (`key_counts.get(&candidate) == 1`). If zero files match, or more than one file shares the same stem (e.g. `mod.rs` in two different directories, or two languages' files that happen to share a stem), the import is silently dropped — no edge, and no signal that it was ambiguous.
5. **Self-edges excluded**: if the resolved target is the same file as the source, it's discarded (`target != path`).
6. **Deduplication**: targets are collected into a `HashSet`, so multiple imports from A to B collapse to one edge; the metric counts distinct target files, not import statement count.

So Ce (efferent) for a file = number of distinct other corpus files it successfully resolves an import to; Ca (afferent) = number of distinct files whose edge set contains it (`count_incoming_edges`); Instability is derived from those two.

## What deliberately does not count

- **Imports of anything outside the corpus** — standard library, third-party packages, anything that isn't one of the files knots parsed in this run. There's no external-module tracking; it's dropped at the module-key lookup (no match in `key_owner`).
- **Ambiguous stems** — any import string that reduces to a module key shared by ≥2 corpus files is treated as unresolvable and produces no edge, rather than guessing or fanning out to all candidates. The file doc calls this out explicitly as "a best-effort heuristic, not real module resolution."
- **Self-imports** — a file "importing" itself never becomes an edge.
- **Files that fail to parse or read** — `extract_file_imports` returns `None` on read/parse/language-lookup failure and is skipped silently (the code comment notes `collect_all_metrics` already warns about the same files elsewhere, so this path doesn't duplicate that warning).
- **Duplicate imports of the same target** — multiple `use`/`import` lines pointing at the same file only ever contribute one edge (HashSet dedup), so Ce/Ca measure distinct-file coupling, not import-statement volume.

One thing the index can't tell me directly: I don't have the actual list of node-kinds `import_sources` treats as "an import" per language (that logic lives in the external `lang_parsing_substrate` crate, not in this repo's indexed source), so I can't say precisely which per-language syntactic forms (e.g. re-exports, conditional/lazy imports, dynamic `require`) are or aren't captured at the extraction step — only what happens to whatever that substrate hands back.
