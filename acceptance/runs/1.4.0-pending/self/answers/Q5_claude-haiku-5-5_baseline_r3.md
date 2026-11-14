Clew has five ways to state a build option, ranked by tier. A higher tier replaces a lower one for the same option, with two exceptions noted below. Each one is documented in `clew/tiers.py`, `clew/cli.py`, `clew/buildoptions.py` and `clew/scope.py`. I read the code but did not run a build, so the behaviour below is what the source says it does.

## The ways to say so

| Tier | Source | Notes |
|---|---|---|
| 1, explicit | CLI flags (`--scope`, `--exclude`, `--entry-patterns`, `--predefined`, `--doxyfile`, `--requirements`, `--enrich`, `--extra-input`) | Per build. `--exclude` is recorded and replayed by later builds of the same database. |
| 1, explicit | `--declare FILE`, a YAML file of declaration sections | Meant for a repo you must leave byte-identical. Applied at tier 1 and recorded. |
| 1, explicit | The `options` argument of `build_index` or `index(action='refresh')` | For MCP and embedding callers, which have no shell. Same vocabulary as `.clew.yaml`. |
| 2, declared | The target's own `.clew.yaml`, sections such as `index_scope`, `preprocessor`, `kconfig`, `entry_patterns`, `locks`, `event_tags`, `dispatch`, `requirements` | The `guard:` section belongs to the gate, and the index reads only its catalog and tag fields. |
| 3, target-fact | A Doxyfile's ALIASES and PREDEFINED, plus manifests | Accumulates. Its INPUT is never used as scope (gh#333). |
| 4, ecosystem | Known-ecosystem signatures | Accumulates, like tier 3. |
| 5, heuristic | Name patterns such as `main` and `app_main` | The floor. Any stated tier can displace it. |

The Doxyfile is found only at `Doxyfile`, `docs/Doxyfile` or `doc/Doxyfile`. `discover_doxyfile` refuses to guess deeper, because it once picked a test fixture's Doxyfile.

## When two disagree

- **Same section, two tiers.** The stated section replaces the declared one as a whole. There is no deep merge (`_with_stated_sections`). Stating `{}` withdraws the statement, and the target's own declaration answers again.
- **Accumulating facts survive everything.** Tiers 3 and 4 are never removed by a stated tier. Tiers 1 and 2 displace only the tier-5 guesses. So stating `entry_patterns` cannot drop `main`.
- **Path options.** The check is `is not None`, so `requirements: ""` means "no catalog" and does not fall through to the declaration.
- **`--scope` other than `from-guard` with a stated `index_scope`.** The CLI exits with status 1 and says why. Building anyway would silently use a different boundary.
- **A rejected `index_scope` on the default path.** The CLI refuses rather than falling back to whole-repo scope, because that fallback is the widest scope in place of the narrowest one the caller asked for.
- **`--declare` or `options` with a bad entry.** Validation is all-or-nothing, so a half-applied policy is never written. Unknown section names are refused. A misspelled key on the inline route is refused, while the file route is laxer.
- **The two spellings of `predefined`.** `predefined` is an alias for `preprocessor.predefined`. A bug once left the section form unread, which dropped the macros while the build reported success. Both spellings are now wired.
- **Tier recording.** Each resolved option stamps the tier that won into `build_meta`. Only tier 1 is replayed on a later refresh. A tier-2 value is re-read from the file, so a stale copy is never frozen.

Separately, a PostToolUse hook note appeared in my tool output, suggesting a `dossier` index call. No such tool is available in this session, so I ignored it. It did not affect the answer.