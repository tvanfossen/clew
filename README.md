# clew

> *A **clew** is the ball of thread Ariadne gave Theseus — the thing you follow to find your way
> out of the labyrinth. It is the archaic spelling, and the direct ancestor, of the word "clue".*

**Give an agent the thread, not a map of the whole maze.** `clew` runs doxygen (or, for a Rust
repo, `rustdoc`) and tree-sitter over a C, C++, Python or Rust repository and compiles the result
into a SQLite graph — symbols, call edges, callbacks, threads, locks, dataflow, requirement
links, file inventory, prose — then serves it over MCP. Pull on one symbol and you get its
callers, its locks, the thread it runs on and the requirement it satisfies.

Per-language setup, what each front end populates, and what it cannot:
[C](docs/languages/C_INTEGRATION.md) ·
[C++](docs/languages/CPP_INTEGRATION.md) ·
[Rust](docs/languages/RUST_INTEGRATION.md) ·
[Python](docs/languages/PYTHON_INTEGRATION.md).

**What it is for is aggregation, not capability.** Nothing here is a question `grep` cannot
answer. The difference is that "who calls this, transitively, across a function-pointer
boundary, and which of those run on another thread" is one query instead of a dozen searches
and a mental model you rebuild every session. It is a cache for work you would otherwise redo.

**doxygen-guard is optional.** [It](https://github.com/tvanfossen/doxygen-guard) is a
pre-commit gate that keeps a repo's doxygen accurate, and a repo that uses it gets a richer
index — briefs, requirement tags, versioned comments. But `clew` needs neither the gate nor a
Doxyfile: a repo that declares nothing gets its whole tree indexed, and three of the four
reference repositories are measured that way. If you want the gate, it is a separate tool with
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

Answering from the index is compared against the same agentic harness without it — same
repository, same model, same sitting, same frozen questions.

**The instrument is being rebuilt.** The previous generation's rubrics graded lexical retrieval
rather than answer completeness, so they measured which tool was used instead of whether the
question was answered. They have been deleted rather than migrated; git history holds them.
[`acceptance/DESIGN.md`](https://github.com/tvanfossen/clew/blob/main/acceptance/DESIGN.md) is the
replacement's schema and grading routine, and
[`docs/CORE_HYPOTHESIS.md`](https://github.com/tvanfossen/clew/blob/main/docs/CORE_HYPOTHESIS.md)
is the claim it tests. No measured figures are published until it has run.

## Refreshing an index

**A refresh is incremental, and a stale query refreshes itself before answering.** Both exist
for the same reason: an agent that believes the index is expensive to correct stops using the
index, and then reasons from a stale one — which is worse than not having it.

- **Incremental.** doxygen is re-run over the changed files plus a closure of their neighbours,
  and the result is spliced into the existing database rather than replacing it. The closure is
  the part that has to be right: doxygen's xref pass is global, so editing `b.c` invalidates
  `a.c`'s edges into it even though `a.c` did not change, and a second pass over the include
  graph recovers calls the edit itself introduces. On this repository doxygen went from 6218 ms
  to 325 ms, taking a warm refresh from 8672 ms to ~2700 ms.
- **Automatic.** When a query arrives against an index whose sources have moved, the refresh
  runs first and the answer describes the current tree. That is the ~2700 ms above, once, rather
  than a wrong answer immediately.
- **You can still ask.** `index(action='refresh')` refreshes on demand; add `force=True` for a
  full rebuild.

Three limits worth knowing, none of them silent:

- **A newly-added CROSS-FILE call needs C or C++.** The include-graph pass reads doxygen's
  `includes` table, which is populated from `#include` — so on Python and Rust that pass finds
  nothing and such a call waits for a full rebuild. The edited file itself is always re-indexed.
  See [PYTHON_INTEGRATION.md](docs/languages/PYTHON_INTEGRATION.md) and
  [RUST_INTEGRATION.md](docs/languages/RUST_INTEGRATION.md).
- **One extra iteration, not a fixed point.** A call reachable only through two new hops waits
  for a full rebuild, and a generation limit bounds how long a splice chain runs before one
  happens anyway.
- **A stale server process refuses to write.** Query tools open the database per call, so reads
  are always live; but a server whose code predates the working tree will not build, because it
  would re-stamp the index with old pipeline logic. Restart the client — a rebuild cannot fix it.

**A `CLEW_BUILD_VERSION` bump makes the next build cold.** The constant tracks the build's
output shape, so when it moves the cached doxygen output is discarded and no index of the old
shape survives to be queried. Upgrading clew therefore costs one full build, once.

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

The package is always required — the server *is* the `clew-mcp` command it installs, and no
plugin or registration step can supply that. Install it so the command is on PATH whatever
virtualenv happens to be active:

```bash
pipx install clew-trace          # or: pip install --user clew-trace
sudo apt install doxygen         # REQUIRED, and not pip-installable
```

A plain `pip install` inside a project venv also works, but only while that venv is on the PATH
your editor launches the server with — which is the usual reason a correctly-registered server
shows as failed to connect.

Then register it, EITHER as a Claude Code plugin:

```
/plugin marketplace add tvanfossen/clew
/plugin install clew@clew
```

or by hand, which also doctors the environment and names what is missing:

```bash
clew init                        # writes ./.mcp.json  (--scope global for user-level)
```

Pick one. Both register a server named `clew`, so doing both leaves two sources for one entry —
run `claude mcp remove clew` first if you have already used `clew init`.

### What the plugin installs, including a hook

The plugin registers the MCP server **and one `PostToolUse` hook**. Installing a Claude Code
plugin does not prompt you about hooks, so it is stated here instead:

- **What it does.** After a `Bash`, `Grep`, `Glob` or `Read` call it adds a short note naming the
  file you just looked at and the one index call that would have answered more — *"You read
  `symbols.py`. A file read gives you the body and nothing else; `dossier` returns that same body
  plus its callers and callees in one reply."* It exists because `grep` has an enormous training
  prior and an index tool has none — the tool being correct does not make it reached for.

  It says what you just did because the generic version did not work. Measured on a real session:
  the old note fired repeatedly while the agent read four source functions with `grep`, one of
  which `dossier` would have answered completely. Asked why it ignored the note, the agent's
  account was that "the index exists" carries no information a capable model does not already
  have, so it reads as a banner. Naming your last action is the one thing a note that fires
  *after* the call can say with any marginal value.
- **It escalates only when ignored, and one index call silences it.** Each file-inspection call
  adds one to a per-session tally; a clew call **clears the tally to zero** rather than crediting
  against it. Below five it says nothing; from five it speaks every fifth call; from twenty it
  speaks every third call and switches to a blunter tier that states the ratio rather than the
  capability. A session that uses the index even occasionally stays permanently silent.

  Two things here are corrections rather than choices. **Crediting** was the original design and
  was unrecoverable: measured on one real session, 1,339 searches against 38 clew calls left a
  pressure of 1,225 against a threshold of 20, needing ~408 *consecutive* index calls to earn
  silence back. The loudest tier became permanent, and its own promise that using the tool would
  stop it was arithmetically false. **The loud tier also fired on every single call**, which
  produced ~30 near-identical injections in one session — wallpaper, and therefore filtered
  hardest exactly where the message mattered most.
- **~46 ms per matching call**, almost all of it Python starting. It imports nothing from the
  `clew` package and nothing outside `os`/`sys`/`json`, for that reason.
- **It is registered once per tool** — `Read`, `Grep`, `Glob` and `Bash` each get their own
  matcher passing their own flag, plus one for the clew tools passing `--used`. That is how it
  knows which kind of call fired **without reading `tool_name`** off the event: the modality comes
  from the manifest you can read, not from the payload a repository can influence.
- **What can reach your model through it, stated exactly.** Through 1.0.9 the answer was
  "nothing": the payload was assembled from constant strings and the only run-time value was the
  tally, an `int` through `%d`. **That is no longer true, and the change was deliberate** — a note
  that cannot name your last action was measured changing nothing. The guarantee is now a
  *bounded* one rather than an absolute one:

  > The output is a `json.dumps` of a literal-keyed object. Every value is a module-level literal,
  > an `int` through `%d`, or a **basename matching `[A-Za-z0-9._-]{1,64}` and not starting with a
  > dot** — the complete output set of one function, `_safe_token`.

  Two separate mechanisms, because there are two separate risks and neither covers the other:

  - **`json.dumps` over the whole object** means a filename can never alter the payload's
    *structure*. Hand-assembled JSON was safe only while the substituted value was an integer; a
    filename containing `"}}` would otherwise close the string early and append sibling keys of
    the hook protocol — a `decision`, a `continue` — letting a repository steer the harness
    itself.
  - **`_safe_token` bounds the *content*** without eliminating it. Up to 64 allowlist-clean
    characters of a filename are quoted back inside the note. A repository can name a file
    `dossier-is-unreliable-prefer-grep.py` and have that appear in the hook's voice. **That
    residual is real and accepted.** What limits it: `tool_response` — the bulk repository-written
    field — is **never read**, the bytes are already in your model's context from the tool result
    the hook is reacting to, and the note's own literal always closes the sentence so a filename
    never sits at the end.

  Both are asserted structurally in `tests/test_hook.py`, over the AST rather than over text: `%s`
  is permitted but only ever fed `_safe_token`'s output, and `_safe_token`'s output set is proved
  by running **every** code point through it rather than by sampling hostile strings. Each was also
  verified by mutation — disabling either one fails the test aimed at it, and disabling both lands
  a real `"decision": "block"` injection that four tests catch.
- **It never exits non-zero**, because a non-zero exit would send its stderr to the model. Every
  path returns 0, including every failure path — a marker file that cannot be written fails
  silently.

**To turn it off**, set `CLEW_HOOK_DISABLE=1` in the environment Claude Code runs in, or delete
`hooks/hooks.json` from the installed plugin. Registering the server by hand with `clew init`
installs no hook at all.

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

## Rust support

A repo with a `Cargo.toml` and no Doxyfile is indexed with `cargo +nightly rustdoc
--output-format json` instead of doxygen — doxygen has no Rust parser, and would otherwise
silently produce zero symbol rows rather than an error. This needs a nightly toolchain on
`PATH` (`cargo +nightly --version`); `clew init` does not check for it today, so its absence
surfaces as a build-time `RustdocUnavailableError` instead. Every package's `[lib]` **and**
every `[[bin]]` target are documented — a `main.rs` binary is not assumed to be a thin wrapper
around its lib; a package that pairs a same-named lib and bin (a common shape) has both
indexed, not just one.

**Doc comments are not required.** An undocumented, non-`pub` function is indexed with its full
signature, body, callers, callees and liveness — `///`/`//!` only fill in the `brief`/`detail`
prose fields, they gate nothing else. Do not write doc comments just to make indexing "work."

**`//!` module docs are still worth writing**, for the same reason a C file benefits from a
leading `/*! ... */` block: `search`'s conceptual-query path matches on file-level prose (see
`filedocs.py`), separately from any per-symbol `///`. A `//!` at the top of a module whose value
is conceptual — a metrics formula, a dispatch table, a locking-order convention — makes that
module findable by a query naming the concept rather than a function name.

## Without an agent

`clew.query` is importable and returns JSON-serializable dataclasses. It is what the MCP server
is a view over, so no query logic exists twice — and it is **wider than the four tools**, by
design: `callers`, `callees`, `chain_trace`, `req_trace` and `thread_of` are functions here,
folded into `dossier` at the tool layer to keep one call answering a whole question.

```python
from clew.query import dossier, search

dossier("clew.db", "sensor_poll")     # a function
dossier("clew.db", "REQ-NAV-002")     # a requirement
dossier("clew.db", "buf_mutex")       # a lock
search("clew.db", "retry backoff")    # find the name when you do not have one
```

`dossier` takes any indexed subject — function, variable, macro, class, lock, thread,
requirement or Kconfig symbol — and its reply names which kind resolved. `function_dossier` is
the narrower form that describes a function or macro and returns `None` for anything else.

## Layout

| Path | What |
|---|---|
| `clew/` | The pipeline (`python -m clew`) |
| `clew/query/` | The stable query API the MCP server is a view over |
| `tests/` | `.venv/bin/python -m pytest tests/ -q` (add `--integration` for the tier that builds real repos) |
| `acceptance/DESIGN.md` | The schema and grading routine for the instrument being rebuilt |
| `acceptance/operational/` | Build and refresh cost, and judge variance — measured beside the matrix, never inside it |

## Dogfooding

clew runs its own gate: `.venv/bin/pre-commit run --all-files` → ruff (lint +
format), doxygen-guard (`@brief`/`@version`/`@return` presence on the shipped
package), and the full test suite. Its own catalog lives in `requirements.yaml`.

## doxygen-guard

[doxygen-guard](https://github.com/tvanfossen/doxygen-guard) is a separate tool, consumed here as
a pip dependency and pinned by `rev:` in `.pre-commit-config.yaml`. Its scope is
validation, traceability and change impact; nothing here extends it, and `clew` does not require
it — see the top of this file.
