**Short answer:** the index holds a file row for every YAML, JSON, shell and CMake file it is handed, plus function and macro definitions for shell and CMake. YAML and JSON contribute no symbols at all. On an installation whose parser lacks the bash or cmake grammar, shell and CMake files are still registered but yield no definitions, and the not-indexed report does not name them. That is the one place the code breaks its own "absence is not emptiness" rule.

**What the index holds, by type**

| Type | `path` row (file set) | Symbols | Source |
|---|---|---|---|
| `.sh`, `.bash` | yes | `memberdef` for `name() {…}` and `function name {…}` only; `args` always empty | `clew/shast.py:9-12`, `clew/synth.py:62` |
| `.cmake`, `CMakeLists.txt` | yes | `function` and `macro` definitions, the macro mapped to doxygen's "macro definition" | `clew/cmakeast.py:9-14`, `clew/synth.py:69` |
| `.yaml`, `.yml`, `.json` | yes | none; "registered and never harvested" | `clew/synth.py:12-15`, `:71-80` |

Shell definitions carry the `#` comment block directly above them as their description. A block separated by a blank line documents nothing.

The index does not hold a YAML or JSON key, a value, or any structure within the file. It does not hold shell variables or arbitrary commands. I did not verify whether shell or CMake call sites produce call edges; the harvesters I read emit definitions only.

**This repository.** It is clew itself, which is Python. A glob found no `.sh`, `.cmake` or `CMakeLists.txt` files. Its YAML and JSON files (`.github/workflows/*.yml`, `hooks/hooks.json`, `.clew.yaml`, and others) appear in the files corpus with `symbol_count: 0`. So the shell-and-CMake premise in the question does not describe this repo. Its YAML and JSON are present but empty.

**What an installation without the grammars does**

The code path is:

1. `register_synth_paths` runs unconditionally on every scanned file (`clew/cli.py:1909`).
2. `claims()` decides on extension alone (`clew/synth.py:191-199`). It never asks whether a grammar exists. So `.sh`, `.cmake` and YAML/JSON all get `path` rows whatever the substrate holds.
3. The shared parse routes `.sh` to `substrate:bash` and `.cmake` to `substrate:cmake`. `_ts_language_for` returns None when the optional key is absent (`clew/harvest.py:203`, `_OPTIONAL_KEYS` at `:145`). No parse runs and no `memberdef` rows are written.
4. The not-indexed report counts only scanned files that lack a `path` row (`clew/cli.py:2668-2684`). Shell and CMake files have one, so they are never named.

Result: a shell-heavy repo on a substrate without `bash` or `cmake` shows its `.sh` files as in the file set with zero symbols, and nothing says they were skipped. That is the silent-empty failure the AGENTS.md "absence is not emptiness" section warns about. I read this from the code and did not run a degraded install to confirm it.

YAML and JSON are never routed to a grammar (they are absent from `_TS_GRAMMARS`, `harvest.py:118-128`), so the presence or absence of the `yaml` and `json` keys changes nothing for clew. They behave the same on every install.

**A doc/code mismatch.** `synth.py:14` says YAML and JSON are "named by the not-indexed report." The code does not do that: they always get `path` rows, so the report never names them.

**Is the degrade signal used?** `substrate.missing_languages` is the one function that reports absent grammars. The index shows no resolved callers, but four unresolved call sites mean that is not proof of non-use. I did not find a consumer that surfaces it to the user.

**This install.** The clew project venv (`/home/tvanfossen/Projects/clew/.venv`) has `bash`, `cmake`, `yaml` and `json` compiled in, so the degraded path does not apply here.

**Suggested fix.** Make `claims()` consult `_grammar_available` for the optional shell and CMake keys, so an absent grammar leaves those files out of `path` and into the not-indexed report. Fix the `synth.py:14` comment or make YAML and JSON actually reported. Neither change is made.