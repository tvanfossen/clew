**Ways to say so**, in order of precedence:

| Route | Where | Scope |
|---|---|---|
| **Tier 1, stated for one build** | `--declare FILE`, or the `options` argument of `build_index()` / MCP `index(action="refresh")` | This build only, but recorded in `build_meta` and replayed by later builds of that database |
| **Tier 2, the repo's standing declaration** | `<repo>/.clew.yaml`, same section names as the flags | Every build of that repo, CLI and MCP alike |
| **Tier 3/4, facts the repo already wrote** | Doxygen `PREDEFINED`/`ALIASES`, generator manifests, language or ecosystem signatures | Accumulate; no declaration removes them |
| **Tier 5, built-in heuristics** | Name-pattern guesses | The floor; any stated tier displaces them |

The `.clew.yaml` sections are `index_scope` (roots/excludes), `preprocessor`, `requirements`, `thread_patterns`, `shared_key_patterns`, `locks`, `dispatch`, `mqtt_dispatch`, `data_model`, `kconfig`, `event_tags`, `entry_patterns`, `enrich`, and similar. The `guard:` section is the gate's and is ignored by the index's declaration loader.

Only six CLI arguments remain: `--output`, `--repo-root`, `--declare`, `--exclude`, `--rebuild`, `--verbose`. Everything else is a declaration. `--exclude` is the exception that is not a declaration: it is recorded into the index and replayed.

**When two disagree**

- **`--declare` or `options` vs `.clew.yaml`:** the stated value wins for that section. The rule is per section, not per file. Other sections in the file still apply. For `index_scope`, the stated block replaces the file's block; it does not merge with it.
- **`index_scope` vs `--scope`:** the default `--scope` is `from-guard`, which reads `index_scope`. Passing any other `--scope` (such as `doxyfile`) while `index_scope` is stated exits 1 with an error. It does not silently override.
- **Empty values:** for manifest options, an empty `{}` states nothing and falls through to the repo's own file. For `preprocessor`, an empty `{}` is a withdrawal, not silence. Withdrawing a recorded statement reverts it.
- **Broken input:**
  - A malformed `.clew.yaml` is logged as a warning and treated as absent, so the build runs on defaults.
  - An unknown section name in `.clew.yaml` raises an error and refuses the build. Silently ignoring it would report a declaration as honoured when nothing read it.
  - An unknown key in `--declare` or `options` exits 2.
  - An `index_scope` that is present but unusable falls back to whole-repo, with a warning naming the rejection.
  - A declared root that does not exist is dropped with a warning.

**Caveats:** I derived this from reading `clew/cli.py`, `declaration.py`, `scope.py`, `tiers.py` and `buildoptions.py`. I did not run a build to confirm the behaviour. The `--exclude`/`index_scope.excludes` combination is inferred from a code comment rather than tested.