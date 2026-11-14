The repository gives clew five ways to change what it indexes, ordered by precedence. Where two disagree, a stated value replaces the defaults for that option and the rest accumulate. Everything below comes from clew's own docs and function docstrings. I did not run a build, and several function bodies are flagged as changed since the index was built, so treat the line-level details as unverified.

**The ways to say so**

| Tier | Source | Combines by |
|---|---|---|
| 1 | CLI flag (`--scope`, `--exclude`, `--entry-patterns`, `--doxyfile`, `--predefined`, …), or the `options` argument an embedding caller passes to `build_index` / `build_or_refresh` | Replaces the stated layer |
| 2 | `.clew.yaml` at the repo root, found via `--repo-root` | Replaces the stated layer |
| 3 | Facts the target already wrote: a Doxyfile's `ALIASES` and `PREDEFINED`, generator manifests, language entry points | Accumulates |
| 4 | Known-ecosystem signatures (UDM, ingot) | Accumulates |
| 5 | Name-pattern heuristics, the floor | Replaced by any stated tier |

The `.clew.yaml` sections and the `options` keys share one vocabulary, so `index_scope`, `preprocessor`, `kconfig` and the rest are the same names in both places. Mechanics such as `--scope`, `--index-cache` and `--rebuild` describe one run, not the repository, so they are flags only.

**When they disagree**

- **Flag against declaration, same option:** the flag wins and the declaration is ignored for that option. `_declared_or_flag` in `clew/cli.py` does this. Section-level values are replaced whole, not deep-merged, so a flag that states `preprocessor: {predefined: [...]}` does not blend with the declared `config_header`.
- **Tier 3 and 4 facts:** these survive every stated tier. The docs say so explicitly. I did not verify that every consumer honours this.
- **Tier 5 heuristics:** any stated tier displaces them. The design exists so that stating `--entry-patterns` cannot silently drop `main`.
- **Empty values withdraw rather than state:** `[]` or `{}` falls through to the declaration, and then to the floor. An empty `options` document changes nothing and is not an error.
- **Doxyfile INPUT versus `index_scope`:** the declaration wins. A Doxyfile is a documentation target, so its `INPUT` is replaced, while its `ALIASES` and `PREDEFINED` are kept. `--scope doxyfile` is the explicit opt-out that indexes the Doxyfile's own `INPUT` list instead.
- **Invalid options:** `apply_options` validates the whole mapping before assigning anything, so one bad entry refuses the whole mapping. A stated `doxyfile` must exist, or the build refuses rather than silently indexing the whole repo.

**Making disagreements visible**

Each build records the winning tier per manifest option in `build_meta`, so `options.<name>.tier` shows whether a flag, the declaration or the floor supplied it. Files in scope with no rows are reported as `not_indexed` counts, so a gap is not mistaken for absence.