Clew has three ways for a repository to state its own indexing conventions. When two of them disagree, the higher tier replaces the lower one for that option, with two exceptions: facts the repository already wrote down are never removed, and every stated value is recorded.

**The ways to say so**

| Tier | How | Scope |
|---|---|---|
| 1, explicit | `--declare FILE` on the CLI, or the `options` argument on `build_index` / `index(action='refresh')` (MCP or in-process) | One build, but replayed by later builds of the same database |
| 1, explicit | `--exclude` (recorded as `scope.operator_excludes` and replayed) | Same as above |
| 2, declared | `.clew.yaml` at the repo root (`clew/declaration.py`) | Standing, re-read on every build |

Each section of `.clew.yaml` is named after its option (`shared_key_patterns`, `thread_patterns`, `locks`, `preprocessor`, `kconfig`, `index_scope`, `sub_indexes`, `event_tags`, `requirements`, `enrich`, `doxyfile`, and so on). `--declare` takes the same document shape. The CLI was cut from 22 build flags to 6 (`--output`, `--repo-root`, `--declare`, `--exclude`, `--rebuild`, `--verbose`), so most conventions are now stated through `--declare` rather than their own flags (`clew/cli.py:420-530`).

Three layers are not stated by anyone. Tier 3 is facts the target already wrote down, such as a Doxyfile's ALIASES or PREDEFINED. Tier 4 is known-ecosystem signatures. Tier 5 is name-pattern heuristics, the built-in default floor.

**What happens when they disagree**

- **Tier 1 beats tier 2.** `_declared_or_flag` returns the stated value whole. For a list-valued option, `resolve_layered` makes the stated list replace the declared one (`clew/tiers.py:300-358`). For a manifest document, the stated document replaces the declared one. Nothing is merged.
- **Within tier 1, inline beats file.** `--declare` is applied first and the `options` argument second, so an inline value overrides the same key from the file (`clew/cli.py:3404-3409`).
- **Tiers 3 and 4 accumulate and survive every stated tier.** A stated `entry_patterns` list cannot remove the built-in `main` entry, because the facts layer always stays in the resolved set. Tier 5 is the only layer a stated value displaces.
- **An empty value is a withdrawal.** `[]` or `{}` at tier 1 falls through to the declaration, then to the defaults. That is how an operator undoes a recorded statement.
- **Unknown input is refused, not ignored.** An unknown section in `.clew.yaml` raises `DeclarationError`. An unknown option key or a misspelled entry key in `options` raises `BuildOptionError`. Refusing is deliberate: an ignored key would let the build report success under defaults.
- **Malformed `.clew.yaml` is softer.** Unparseable YAML is logged at WARNING and treated as absent, so the build falls back to defaults.
- **A stated `doxyfile` must exist.** Otherwise the build would silently index a different source set. A missing `requirements` or `enrich` file only degrades metadata, so the loader reports it and the build continues.
- **Tier 1 is recorded and replayed.** Each build stamps `options.<name>.tier` into `build_meta`. Only a tier-1 statement is written out in full and replayed by later builds of that database. A declaration is not frozen: tier 2 is re-read from the file each build.

I read these rules from the code and did not run a build to confirm them. The behaviour is documented in the docstrings of `clew/tiers.py`, `clew/buildoptions.py`, `clew/declaration.py` and `clew/cli.py`.