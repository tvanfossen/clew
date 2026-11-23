There are three layers to configure with, and they resolve differently. Explicit statements override the repo's standing declaration. Facts already written in the repo, such as a Doxyfile, add to the result rather than replacing it. Heuristics are only a floor.

**Ways to say so**

| Tier | Source | How it combines |
|---|---|---|
| 1 | CLI flags (`--doxyfile`, `--exclude`, `--entry-patterns`, `--scope`, `--declare <file>`), or the `options` argument for embedding callers | Replaces the layer below it |
| 2 | `.clew.yaml` at the repo root | Replaces the layer below it |
| 3 | Facts someone else wrote: a Doxyfile's `ALIASES`/`PREDEFINED`, generator manifests, language entry points | Accumulates |
| 4 | Known-ecosystem signatures | Accumulates |
| 5 | Name-pattern heuristics | Replaced by any stated tier |

Sources:
- **Tier 1** goes through one validator, `apply_options` in `clew/buildoptions.py`. It checks every entry before assigning any, so one bad entry leaves the build untouched. `--declare` and the `options` argument share this route.
- **Tier 2** is `.clew.yaml`, read by `load_declaration_located` in `clew/declaration.py`. Its `guard:` section belongs to the gate and is dropped before the index reads the file.
- **Scope** is `index_scope:` in `.clew.yaml`, with `roots` (required) and `excludes`. Without it, the whole repository is indexed. Under `--scope from-guard` (the default), a Doxyfile's `INPUT` is replaced, so the Doxyfile supplies `ALIASES`/`PREDEFINED` and not the file list. `--scope doxyfile` is the explicit opt-out that uses the Doxyfile's `INPUT`.
- **Doxyfile discovery** only checks `Doxyfile` at the root, `docs/` and `doc/`. It refuses to guess among stray Doxyfiles, because one once selected a test fixture.

**When two disagree**

- **CLI flag vs `.clew.yaml` (same option):** the flag wins outright. The declaration is not merged in. The declaration stays on disk, and the build records that tier 1 won. Passing an empty list is a withdrawal, not a statement: it falls through to the declaration, then to the heuristics.
- **`.clew.yaml` vs a Doxyfile:** for scope, the declared `index_scope` wins over the Doxyfile's `INPUT`. For `ALIASES`/`PREDEFINED`, both apply, because facts accumulate.
- **Tier 3 or 4 vs anything stated:** no conflict. Facts always survive, so a stated `--entry-patterns` cannot drop `main`, which was the bug that motivated this design.
- **Errors in the declaration itself:**
  - An unknown top-level section refuses the whole build, naming the section, so a misspelling cannot silently fall back to defaults.
  - An unknown key inside `index_scope` is rejected with a warning, and the build falls back to the whole repository. That is a quieter failure than a refusal.
  - A declared path that does not exist is refused when stated through `options` or `--declare`.

**Inconsistency I found:** `_resolve_doxyfile_and_root` in `clew/cli.py` handles a bare `--doxyfile` that does not exist by logging a warning and ignoring it, then synthesizing a Doxyfile. The `options` route refuses the same input. The code comment calls the warn-and-ignore path a fix, so this may be intentional, but the two entry points disagree.

I cited files and functions rather than line numbers. Several index entries reported line drift, so I did not check exact lines in the working tree.