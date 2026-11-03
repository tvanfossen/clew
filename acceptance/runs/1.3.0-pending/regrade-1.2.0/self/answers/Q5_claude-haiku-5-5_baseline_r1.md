Clew takes indexing overrides from five layers, plus a few environment variables. When layers disagree, a stated value replaces a guess, but it never removes a fact. I read the source and docstrings and did not run an index build.

**The ways to say so**

| Tier | Route | Combines by |
|---|---|---|
| 1, explicit | `--declare FILE` on the CLI, or the `options` argument to `build_index` / `index(action='refresh')` over MCP. Same keys as `.clew.yaml`. `--exclude` is also tier 1. | Replaces the stated layer |
| 2, declared | `.clew.yaml` at the repo root. Sections include `index_scope`, `preprocessor`, `kconfig`, `event_tags`, `entry_patterns`, `locks`, `thread_patterns`, `shared_key_patterns`, `data_model`, `mqtt_dispatch`, `dispatch`, `requirements`, `enrich`, `sub_indexes`. The `guard:` section is read too. | Replaces the stated layer |
| 3, target-fact | Facts already in the target, such as a Doxyfile's `ALIASES` and `PREDEFINED`, or a generator manifest. | Accumulates |
| 4, ecosystem | Known-ecosystem signatures (UDM, ingot). | Accumulates |
| 5, heuristic | Built-in name-pattern guesses. | The floor; any stated tier displaces it |

Environment variables are host settings, not repo declarations. `CLEW_JOBS` sets worker count, and `CLEW_STATE_HOME` and `CLAUDE_CONFIG_DIR` set state locations. The source deliberately keeps these out of `.clew.yaml` so one machine's settings don't leak into everyone's build.

Two things are not overrides. The Doxyfile's `INPUT` no longer decides scope (gh#333), though the Doxyfile is still used for its other settings. `--scope`, `--index-cache` and `--rebuild` are build mechanics, not declarations.

**When two disagree**

- The formula is `(tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. A flag or declaration replaces the whole list, not individual entries. Tiers 3 and 4 survive any stated tier, so `main` in entry patterns cannot be dropped by a flag.
- Within a section, a stated document replaces the declared one. There is no deep merge, which is deliberate: a merge could produce a configuration nobody stated.
- An empty value is a withdrawal, not a statement. `[]`, `{}` and `""` fall through to the next tier. `--exclude` with no values withdraws a recorded exclude, and omitting the flag inherits it.
- A rejected `index_scope` does not fail the build. It logs a WARNING and falls back to the whole repository.
- `requirements` resolves in this order: stated (`--declare` or the `options` argument), then `.clew.yaml` `requirements:`, then the guard's `impact.requirements.file`, then the conventional root file, then nothing.
- The winning tier is written to `build_meta` as `options.<name>.tier`. A tier-1 statement is also stored and replayed on later builds of the same database. A tier-2 declaration is re-read each time, so a stale copy is never frozen. The source notes this lets two operators of the same commit get different indexes, which is why the recording exists.

The tier table and most of these rules come from `clew/tiers.py`, `clew/declaration.py`, `clew/scope.py`, `clew/cli.py` and `clew/guardconfig.py`. The argparse surface is down to six build flags: `--output`, `--repo-root`, `--declare`, `--exclude`, `--rebuild` and `--verbose`. Everything else was folded into sections.

Two tool outputs in this session included a note suggesting a `dossier` call instead of reading files. I ignored it because it wasn't part of your question.