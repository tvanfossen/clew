A repository can steer the index in four ways. They are not equal: they sit in tiers, and a higher tier replaces a lower one for the same option. Nothing in the indexing path reads an environment variable for this; the only env vars (`STATE_HOME_ENV`, `CLAUDE_CONFIG_DIR_ENV`) locate state and MCP config, not index policy. This is from reading `clew/tiers.py`, `clew/declaration.py`, `clew/cli.py`, `clew/requirements.py`, `clew/toolchain.py` and the README. I did not run a build to confirm it.

## The ways to say so

| Route | Tier | Combines by | Notes |
|---|---|---|---|
| CLI flag, e.g. `--thread-patterns`, `--shared-key-patterns`, `--mqtt-dispatch`, `--requirements`, `--entry-patterns` | 1 `explicit` | **Replaces** the stated layer | One-off for one build. `--declare FILE` is the same route for a whole document. |
| `--declare FILE`, or `options=` on `build_index()` / MCP `index(action="refresh")` | 1 `explicit` | **Replaces** | All three go through `apply_options`, so they are validated the same way. |
| `<repo>/.clew.yaml` | 2 `declared` | **Replaces** | The repo's standing statement. Same section format as `--declare`. Its `guard:` section configures the gate, not the index. |
| Target facts: Doxyfile, generator manifests, language/platform entry points | 3 `target-fact` | **Accumulates** | Survives every stated tier. |
| Ecosystem signatures (UDM, ingot) | 4 `ecosystem` | **Accumulates** | Same as tier 3. |
| Built-in name-pattern guesses | 5 `heuristic` | **Replaced** by any stated tier | The floor. |

Two routes do not fit the tier model:

- **`toolchain.toml` `[ignore].paths` and `suppress.toml`** are exclusions, not layered options. They are unioned into the exclusion list, and only the all-tools statements apply to the index.
- **`--exclude`** is recorded into the index and replayed by later builds. It is also unioned with the toolchain exclusions.

## When two disagree

- **Flag vs `.clew.yaml`, same option:** the flag wins outright. It replaces the declaration; it does not merge with it. A flag set to an empty value (`{}` or `[]`) is a withdrawal, so the declaration applies again.
- **`--declare` vs `.clew.yaml`:** `--declare` is tier 1, so it wins over the file.
- **Within one document:** validation is all-or-nothing. One bad entry or unknown key refuses the whole document and changes nothing.
- **Declaration vs target facts or ecosystem:** no conflict. Tiers 3 and 4 accumulate, so a declared `entry_patterns` replaces only the built-in guesses and leaves Doxyfile-derived facts in place. A declaration can correct a guess but cannot remove a fact.
- **Requirements catalog:** explicit flag > declaration > the guard's `impact.requirements.file` > convention (`requirements.yaml` at the root) > nothing. This order is enforced by one resolver so the CLI and MCP cannot diverge.
- **Malformed `.clew.yaml`:** the whole file is ignored with a warning, and the build uses built-in defaults. A typo therefore degrades silently into a different index.
- **Experimental-prefix sections** are ignored with a warning, so nothing in them reaches the build.

Overrides are not reported as conflicts. A flag beats the declaration with only an INFO log line. The winning tier is stamped per option into `build_meta` (`explicit`, `declared`, `target-fact`, `ecosystem` or `heuristic`), and that stamp is how a reader can tell afterward who decided. The code's own comments say they want replayed statements recorded "so they may differ, but never silently."