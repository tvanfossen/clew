<!-- SPDX-License-Identifier: MIT -->
# Shell, CMake, YAML and JSON

| | |
|---|---|
| front end | **clew's own parse** (`clew/synth.py`), from lang-parsing-substrate's bash and cmake grammars |
| extensions | shell `.sh` `.bash` · CMake `CMakeLists.txt` `.cmake` · data `.yaml` `.yml` `.json` |
| requires | a substrate build carrying the `bash` and `cmake` grammars — see **Availability** |
| provenance | rows carry `dg_source = 'parse'` |

doxygen reads none of these. Shell is where a repository keeps its deploy, release and
bootstrap logic, and `CMakeLists.txt` is where it says what it builds — frequently the first
thing a reader asks about, and until 1.1.0 the only code in an indexed tree with no rows at
all.

## Four file types, three treatments

The request behind this was "index shell, CMake, YAML and JSON". Those four words mean
different things, so they get different answers:

| file type | has a function concept? | what the index gives it |
|---|---|---|
| `.sh` `.bash` | yes — `function_definition` | `memberdef` rows, doc from the `#` block |
| `CMakeLists.txt` `.cmake` | yes — `function_def`, `macro_def` | `memberdef` rows; a macro is recorded as a macro |
| `.yaml` `.yml` `.json` | **no** | a `path` row: in the file set, no symbols |

YAML and JSON offer `block_mapping_pair` and `pair`. Writing those as symbols would put
every `steps:` key of every workflow file into the namespace that answers
`dossier("my_function")` — thousands of rows that are not symbols, drowning the ones that
are. What those files need is to be **visible**: findable by name, and named by the
not-indexed report when a query finds nothing.

Markdown is not here. It is prose, and `clew/prose.py` ingests every markdown file in the
build's scanned set into the full-text corpus, reachable through `search(corpus='prose')`.

## What becomes a symbol

| Source | Row |
|---|---|
| `deploy() { … }` | `memberdef` function |
| `function rollback { … }` | `memberdef` function |
| `function(add_firmware NAME)` | `memberdef` function, `argsstring` `(NAME)` |
| `macro(strict_warnings TARGET)` | `memberdef` **`kind = 'macro definition'`** |

A shell function has no parameter list — arguments arrive as `$1` and `$@` — so `argsstring`
is empty. That is a fact about the language rather than a gap in the harvest. CMake declares
named parameters, so those are reported.

A CMake `macro` pastes its body into the caller's scope, where a `function` gets its own; a
reader chasing a variable that leaks out of one needs to be told which it was, so the two are
not flattened together.

## Documentation is the `#` block above

Neither language has a comment form doxygen recognises, so the convention is the `#` block
immediately above the definition, with no blank line between:

```sh
# Deploy the built artefact to one target.
#
# @version 2
deploy() {
  rsync -a build/ "$1"
}
```

A detached block (separated by a blank line) documents nothing, which is the rule every other
front end here applies to its own comment form. Tags inside the block are kept as literal
text, exactly as doxygen keeps a tag it does not define. A shebang is not documentation — it
addresses the kernel — so a block that reaches one stops there.

## Availability

These grammars are **not in the published substrate wheel**. They are registered in a fork,
open upstream as a pull request, and clew asks the installed substrate what it can parse
rather than comparing versions — the fork's wheel reports the same version string as the
published one, so a version test would be worthless.

With a substrate that lacks them:

* `.sh` and CMake files are registered in the file set and carry **no symbols**,
* nothing raises, and
* the not-indexed report on an empty answer names those file types, so a caller is told to
  read the file instead of trusting the negative.

When the grammars are published, clew's dependency range moves and the front ends begin
producing rows with no code change.

## Scope note: dot directories

The scope walk prunes every dot directory, so `.github/workflows/*.yml` is **not** in scope on
any tier. The YAML a repository keeps in `conf/`, `deploy/` or at its root is indexed; its CI
workflows are not.
