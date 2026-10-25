Clew has three layers of configuration, and when they disagree the more explicit one wins, but only for the options it actually states. Everything below comes from reading the code and README; I did not run a build to confirm it.

**The ways to say so**

| Tier | Source | How it's stated | Combines by |
|---|---|---|---|
| 1 | Stated for this build | `--declare FILE` (a YAML document with the same sections as `.clew.yaml`), `--exclude PATH…`, or the `options` argument for an embedding caller or MCP | Replaces the tier below |
| 2 | Repo's standing declaration | `<repo>/.clew.yaml`, sections such as `index_scope`, `preprocessor`, `requirements`, `entry_patterns`, `test_paths`, `kconfig`, `doxyfile` | Replaces the tier below |
| 3 | Facts already written down | A Doxyfile's aliases and predefines, generator manifests, language or platform entry points | Accumulates |
| 4 | Known-ecosystem signatures | e.g. UDM or ingot conventions | Accumulates |
| 5 | Built-in defaults | Name-pattern guesses, and the whole-repo scope when nothing is declared | Replaced by any stated tier |

The CLI was cut to six flags: `--output`, `--repo-root`, `--declare`, `--exclude`, `--rebuild`, `--verbose`. Per-option flags such as `--entry-patterns` are gone, so anything beyond those six goes through `--declare` or `.clew.yaml`. The `guard:` section of `.clew.yaml` belongs to the gate; the index reads only the `@req` id pattern and the requirements catalog from it.

**When two of them disagree**

- **Tier 1 vs tier 2, same option:** tier 1 wins. The replacement is per section, not a deep merge, so a stated `preprocessor:` replaces the declared one whole rather than merging keys (`cli.py`, `_with_stated_sections`).
- **Empty means withdraw:** `{}` or `[]` for a stated option falls through to the tier below it. For tier 1 specifically, an absent flag inherits the statement recorded by the previous build, while an empty one clears it. Only tier 1 is replayed; tier 2 is re-read from the file on every build, so a stale copy is never frozen in.
- **Tier 3 and 4 cannot be displaced:** a stated list does not remove the built-in `main` entry point, for example. Stated tiers only override guesses.
- **Requirements catalog path:** precedence is stated `--declare` value, then the `requirements:` section, then the guard's `impact.requirements.file`, then the conventional root file, then nothing.
- **Unknown section name in `.clew.yaml` or `--declare`:** the build refuses with a `DeclarationError`, because an unread section would otherwise be reported as honoured.
- **Unparseable YAML:** a warning, and the file is treated as absent.
- **Invalid `guard:` section:** the gate refuses it with exit 1; the index warns and runs on its defaults.
- **`index_scope` with `--scope`:** a stated `index_scope` paired with any `--scope` other than `from-guard` is refused, since that path would ignore it. A malformed `index_scope` falls back to whole-repo scope with a logged reason.