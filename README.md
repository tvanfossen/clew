# clew

> *A **clew** is the ball of thread Ariadne gave Theseus — the thing you follow to find your way
> out of the labyrinth. It is the archaic spelling, and the direct ancestor, of the word "clue".*

**Give an agent the thread, not a map of the whole maze.** `clew` runs doxygen and tree-sitter
over a C, C++ or Python repository and compiles the result into a SQLite graph — symbols, call
edges, callbacks, threads, locks, dataflow, requirement links, file inventory, prose — then
serves it over MCP. Pull on one symbol and you get its callers, its locks, the thread it runs on
and the requirement it satisfies.

**What it is for is aggregation, not capability.** Nothing here is a question `grep` cannot
answer. The difference is that "who calls this, transitively, across a function-pointer
boundary, and which of those run on another thread" is one query instead of a dozen searches
and a mental model you rebuild every session. It is a cache for work you would otherwise redo.

**doxygen-guard is optional.** [It](https://github.com/tvanfossen/doxygen-guard) is a
pre-commit gate that keeps a repo's doxygen accurate, and a repo that uses it gets a richer
index — briefs, requirement tags, versioned comments. But `clew` needs neither the gate nor a
Doxyfile: a repo that declares nothing gets its whole tree indexed, and three of the four repos
in `acceptance/targets/` are measured that way. If you want the gate, it is a separate tool with
one job; if you do not, this still works.

## The four tools

An agent is the user, and these are the whole of what the server exposes. A human-facing browser
over the index is deliberately deferred: repository searchability for a person is what an IDE
already is, so building a second one is not where the value is.

| tool | for |
|---|---|
| **`dossier`** | Everything about one named symbol in ONE reply: body excerpt, brief, both edge directions, locks held, the thread it runs on, requirements and covering tests, liveness. There is no separate `callers` or `chain_trace` tool — this is why. |
| **`search`** | Find the name when you do not have one, or enumerate a whole layer. `corpus=` picks: symbols, prose, files, config, locks, threads. An empty result is graded and says what it did *not* read. |
| **`index(action=…)`** | Administration, not questions: `refresh` builds, `status` diagnoses, `targets` lists every indexed repo, `stats` grades one, `cull` deletes aged-out databases. |
| **`propose_declaration`** | Reads the repo's evidence and proposes a `.clew.yaml`, entirely as comments, for when a causal layer looks emptier than the code warrants. |

Every reply names the `target` it answered from, and carries a `staleness` block only when that
index is actually stale — so a current index costs nothing to establish.

Reads are live: query tools open the database per call. Writes are refused when the server
process predates its own source, because a build through stale logic can silently drop whole
layers and then report success.

## What's in the database

| Layer | Answers |
|---|---|
| Structure | "what is this symbol?" — doxygen symbol tables, briefs, extents |
| Prose | "*why* does this subsystem exist?" — README/docs markdown, FTS5-indexed |
| Call graph | "who calls this, and how sure are we?" — doxygen ×2 + tree-sitter, every edge carrying `source` + `confidence` |
| Callbacks | "who reaches it through a function pointer?" — registration→dispatch resolution |
| Shared-key dataflow | "writing this key affects whom?" — data-model / queue edges the call graph cannot see |
| **Threads** | "which thread does this run on?" — spawn-site harvest + membership closure |
| **Dispatch semantics** | inline vs queued vs keyed; edge-triggered; **which hops cross a thread boundary** |
| **Terminus** | where a chain leaves the repo through an externally-registered callback |
| Requirements | "what implements / tests REQ-X?" — `@req` traceability |
| Liveness | "does this code even run?" — reachability over the non-fuzzy call graph |

The point of the semantic layers (threads, dispatch mode, terminus) is **causal
chains**: reconstructing "message arrives → who handles it → where it goes →
which thread hops → where it leaves the library → what requirements it touches"
as a single query, not a manual archaeology session.

## Measured

Answering from the index is compared against an agent with only `Read`/`Grep`/`Glob`/`Bash` —
same repository, same model, same sitting, same frozen questions. Four repositories, both arms,
two model tiers. Every transcript, metric and per-mark grade is committed beside its rubric in
[`acceptance/targets/`](https://github.com/tvanfossen/clew/tree/main/acceptance/targets); the results are in each target's `result.md`.

Run it on yours: [`acceptance/targets/TEMPLATE/`](https://github.com/tvanfossen/clew/tree/main/acceptance/targets/TEMPLATE) has the rubric
template and the runbook.

## What semver covers

**Covered** — a breaking change here means a major bump:

- the `clew` CLI verbs and their flags (`init`, `propose`, `export`, and the
  build invocation)
- the MCP **tool names and their wire keys** — a consumer reads `edge_class`,
  `confidence`, `source` and friends by name
- `clew.query`'s public functions and the dataclasses they return

**Not covered**, and deliberately so:

- **the SQLite schema.** `CLEW_BUILD_VERSION` exists precisely because the
  schema moves; a consumer detects a stale index by comparing it, not by assuming
  stability. Query through `clew.query`, not with your own SQL.

  `CLEW_BUILD_VERSION`, `read_build_signature` and `index_unusable_reason` are
  re-exported from `clew.query` and are therefore **covered**, so the documented
  way to check freshness does not reach into an internal:

  ```python
  from clew.query import CLEW_BUILD_VERSION, read_build_signature

  if read_build_signature("clew.db") != CLEW_BUILD_VERSION:
      ...  # rebuild: this index predates the current pipeline
  ```
- `clew.*` internals — anything not re-exported from `query`
- the `.idxcache` format

## Install

The package is always required — the server itself is the `clew-mcp` command it installs:

```bash
pip install clew-trace           # installs the `clew` and `clew-mcp` commands
sudo apt install doxygen         # REQUIRED, and not pip-installable
```

Then register the server, EITHER as a Claude Code plugin:

```
/plugin marketplace add tvanfossen/clew
/plugin install clew@clew
```

or by hand, which also doctors the environment and reports what is missing:

```bash
clew init                        # writes ./.mcp.json  (--scope global for user-level)
```

Pick one. Both register a server named `clew`, so doing both leaves two sources for one
entry — if you have run `clew init` already, `claude mcp remove clew` before installing the
plugin.

`doxygen` is a C++ binary, so it cannot be a Python dependency — `clew init` checks for it and
tells you if it is missing. Everything else, including the MCP SDK, comes with the package.

### Working on clew itself

```bash
python3 -m venv .venv
.venv/bin/pip install -e .[dev]   # pipeline + doxygen-guard + gates
sudo apt install doxygen          # external binary (plantuml optional)
```

## Build a database

```bash
.venv/bin/python -m clew \
    --output clew.db \
    --repo-root /path/to/repo
```

That is the whole common case. The Doxyfile is discovered, and a repo that ships none gets
one synthesized over its declared scope.

**Six arguments, and only six:**

| Flag | For |
|---|---|
| `--output` | where the database is written |
| `--repo-root` | the repository to index |
| `--declare FILE` | a declaration document stated for this build (see below) |
| `--exclude PATH…` | paths to leave out; recorded into the index and replayed by later builds |
| `--rebuild` | ignore every cached entry, then re-warm the cache |
| `--verbose` | more on stderr; changes nothing that reaches the index |

Everything a target repo can *declare* lives in one place — its own
`.clew.yaml` — and `--declare` states the same document for a repository you do
not own and must leave byte-identical:

```yaml
# a --declare document, or <repo>/.clew.yaml
index_scope:          {roots: [src, include], excludes: [src/generated]}
preprocessor:         {predefined: [MY_FEATURE_C], config_header: auto}
requirements:         docs/requirements.yaml
thread_patterns:      {spawns: [{name: osThreadNew, entry_arg_index: 0}]}
shared_key_patterns:  {writers: [{name_prefix: Store_Set}], readers: [{name_prefix: Store_Get}]}
locks:                {locks: [{name: MyGuard, form: raii}]}
dispatch:             {interfaces: [...]}
mqtt_dispatch:        {subscribe_functions: [...]}
data_model:           tools/dm_full.toml
kconfig:              {path: Kconfig}
event_tags:           {emits: produce, handles: consume}
entry_patterns:       ["%trampoline%", "on_%"]
enrich:               docs/architecture_topics.yaml
```

Nothing about a target repo is hardcoded: every section above is a declared override of
a built-in default. The identical mapping is the `options` argument of `build_index()` and
of the MCP `index(action="refresh")` tool, so an agent with no shell can state any of it.

The repo's `.doxygen-guard.yaml` — which supplies the declared `@req` id pattern and the
catalog column mapping — is **discovered** from `--repo-root`: its root, then the path the
doxygen-guard pre-commit hook names in its own `--config` argument, then
`conf/ | config/ | .config/`.

### Commit what you stated

`--declare` reads a document in; `export` writes one out, so a discovery made against a
repository you do not own can be committed to one you do:

```bash
.venv/bin/python -m clew export --index clew.db          # to stdout
.venv/bin/python -m clew export --index clew.db --output .clew.yaml
```

It emits **only what was stated** — never the built-in defaults. That is deliberate: a file
asserting you declared every default would freeze those defaults into your repo, so a later
improvement to one would be shadowed by a value nobody remembers committing. An index that
recorded no statement exports a document that says so.

## Without an agent

The same four capabilities are importable, returning JSON-serializable dataclasses. This is what
the MCP server is a view over, so no query logic exists twice.

```python
from clew.query import dossier, search

dossier("clew.db", "sensor_poll")    # identity, reqs, both edge directions, locks, threads, liveness
search("clew.db", "retry backoff")   # find the name when you do not have one
```

## Layout

| Path | What |
|---|---|
| `clew/` | The pipeline (`python -m clew`) |
| `clew/query/` | The stable query API the MCP server is a view over |
| `tests/` | `.venv/bin/python -m pytest tests/ -q` (add `--integration` for the tier that builds real repos) |
| `acceptance/targets/<t>/<version>/` | Frozen rubrics and the committed results of every grid run against them |
| `acceptance/bench/` | The harness. Acceptance-only by design — deliberately NOT in the pre-commit gate |

## Dogfooding

clew runs its own gate: `.venv/bin/pre-commit run --all-files` → ruff (lint +
format), doxygen-guard (`@brief`/`@version`/`@return` presence on the shipped
package), and the full test suite. Its own catalog lives in `requirements.yaml`.

## doxygen-guard

[doxygen-guard](https://github.com/tvanfossen/doxygen-guard) is a separate tool, consumed here as
a pip dependency and pinned by `rev:` in `.pre-commit-config.yaml`. Its scope is
validation, traceability and change impact; nothing here extends it, and `clew` does not require
it — see the top of this file.
