# Q1 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f -name "*.py" | xargs grep -ln "doxygen" -i | head -50
- **got:** ~/ddb-targets/self/acceptance/bench/bench_arms.py ~/ddb-targets/self/doxyguard_db/ast_symbols.py ~/ddb-targets/self/doxyguard_db/filedocs.py ~/ddb-targets/self/doxyguard_db/dominated_edges.py ~/ddb-targets/self/doxyguard…

### 2. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/doxygen.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Doxygen invocation, output handling, and Doxyfile parsing. 3	 4	`run_doxygen` spawns the doxygen binary with our augmented Doxyfile, 5	streams its stdout to drive a Rich progress bar…

### 3. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Resolve the index scope: a declaration, else the whole repository. 3	 4	TWO tiers, and the Doxyfile is no longer one of them (gh#333). The first is the 5	repo's own `index_scope:` — …

### 4. `Grep`
- **asked:** pattern=derive_scope|replace_input=True|extra_input=, path=~/ddb-targets/self/doxyguard_db
- **got:** ~/ddb-targets/self/doxyguard_db/init_command.py:342:    from .scope import derive_scope ~/ddb-targets/self/doxyguard_db/init_command.py:347:    derived = derive_scope(repo_root) ~/ddb-targets/self/doxyguard_db/scope.py:1…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 600	## @param scope The scope whose roots become the INPUT list. 601	## @version 1 602	## @req REQ-DDB-CLI-001 603	def _fold_scope_into_args(args: argparse.Namespace, scope: DerivedScope) -> None: 604	    """ONE fold for…

### 6. `Grep`
- **asked:** pattern=def load_declaration_located|DECLARATION_NAME|GUARD_CONFIG_NAME|PASSTHROUGH_TOOL|x-doxyguard-db|def load_declaration\b, path=~/ddb-targets/self/doxyguard_db/declaration.py
- **got:** 58:    GUARD_CONFIG_NAME as GUARD_CONFIG_NAME, 65:DECLARATION_NAME = ".doxyguard-db.yaml" 80:## The tool name the passthrough key is suffixed with: `x-doxyguard-db`. Matches the 82:PASSTHROUGH_TOOL = "doxyguard-db" 262:d…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/declaration.py
- **got:** 260	## @version 6 261	## @req REQ-DDB-CONFIG-001 262	def load_declaration( 263	    repo_root: Path | str | None, guard_config: Path | str | None = None 264	) -> dict[str, Any]: 265	    """@brief Read the target's declare…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 760	    that is applied and recorded but not read back is discarded by the next refresh, 761	    which then reports success and a healthy coverage ratio over exactly the content 762	    the operator removed. 763	 764	   …

### 9. `Grep`
- **asked:** pattern=index_scope, path=~/ddb-targets/self/doxyguard_db/mcp_server
- **got:** ~/ddb-targets/self/doxyguard_db/mcp_server/emptiness.py:68:payload) and ending in "Declare `x-doxyguard-db: index_scope:` …" — operator ~/ddb-targets/self/doxyguard_db/mcp_server/emptiness.py:160:    ~840-byte paragraph …

### 10. `Grep`
- **asked:** pattern=index_scope|index-scope, path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 305:##   * `extra_input` / `extra_exclude` — absorbed by `index_scope:` (`roots:` / `excludes:`), 400:            "every declared convention: index_scope, preprocessor (predefined, " 422:            "CONVENTIONS (locks, …

### 11. `Bash`
- **asked:** command=grep -n "add_argument.*index.scope\|dest=\"index_scope\"\|'index_scope'" ~/ddb-targets/self/doxyguard_db/cli.py
- **got:** (Bash completed with no output)

### 12. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 2030	## @req REQ-DDB-MCP-004 2031	## @req REQ-DDB-CONFIG-008 2032	def _run_pipeline(args: argparse.Namespace) -> None: 2033	    """Build into a sibling temp DB, then os.replace() it onto --output. 2034	 2035	    The swap…

### 13. `Grep`
- **asked:** pattern=setattr\(args|args\.declare|def apply_options|INDEX_SCOPE_SECTION" ,|getattr\(args, INDEX_SCOPE_SECTION" , path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 987:        setattr(args, name, str(resolved if resolved.is_absolute() else repo_root / resolved)) 1093:        setattr(args, option, recorded) 2204:        args.declare = str(declare)

**Reasoning.** This is enough context — the "stated" tier is a document merged onto `args` for programmatic callers (e.g. `build_index(options=...)` / MCP), separate from the on-disk declaration file. That's a secondary detail; the core chain is established. Writing the final answer now.

## Answer

**Where the decision is made**

The file set handed to the external `doxygen` binary is decided in two cooperating places:

1. **`doxyguard_db/scope.py`, `derive_scope()`** (`doxyguard_db/scope.py:166-191`) resolves the *INPUT roots* and *EXCLUDE* paths. It is invoked (with logging) as `derive_scope_logged()` fro

---

## Final answer as submitted

This is enough context — the "stated" tier is a document merged onto `args` for programmatic callers (e.g. `build_index(options=...)` / MCP), separate from the on-disk declaration file. That's a secondary detail; the core chain is established. Writing the final answer now.

## Answer

**Where the decision is made**

The file set handed to the external `doxygen` binary is decided in two cooperating places:

1. **`doxyguard_db/scope.py`, `derive_scope()`** (`doxyguard_db/scope.py:166-191`) resolves the *INPUT roots* and *EXCLUDE* paths. It is invoked (with logging) as `derive_scope_logged()` from the CLI's `_apply_scope()` (`doxyguard_db/cli.py:622-677`), which folds the result into `args.extra_input` / `args.extra_exclude` / `args.replace_input` via `_fold_scope_into_args()` (`doxyguard_db/cli.py:603-614`).
2. **`doxyguard_db/doxygen.py`, `_build_doxyfile_content()`** (`doxyguard_db/doxygen.py:512-592`) is where those resolved roots are actually written into the Doxyfile text that gets piped to `doxygen -` on stdin (`doxyguard_db/doxygen.py:844-863`, `run_doxygen()`).

So: `scope.py` decides *what the boundary is*; `doxygen.py` decides *how that boundary becomes the doxygen INPUT/EXCLUDE/FILE_PATTERNS the tool receives*.

**Every input that can influence the file set, and who wins**

In descending precedence:

1. **`--scope` CLI flag.** If it is anything other than `from-guard` (e.g. `doxyfile`), none of the scope-derivation machinery below runs at all — `_apply_scope()` returns early and the target's own Doxyfile `INPUT` is left untouched (`doxyguard_db/cli.py:642-663`). If a stated `index_scope` was also passed in this mode, the CLI refuses outright rather than silently discard it (`doxyguard_db/cli.py:644-662`).
2. **A "stated" `index_scope`** — a scope dict supplied programmatically (e.g. by `build_index(options=...)` / the MCP path) rather than read from a file. Read only under `--scope from-guard`, and only this tier is checked first (`doxyguard_db/scope.py:451-458, 474-478`; threaded in at `doxyguard_db/cli.py:664-677`).
3. **`.doxyguard-db.yaml`'s own `index_scope:` section** at the repo root — read next if nothing was stated (`doxyguard_db/declaration.py:307-311`, consumed at `doxyguard_db/scope.py:414-481`).
4. **The doxygen-guard config's `x-doxyguard-db` passthrough `index_scope:`** — read only when there is no dedicated `.doxyguard-db.yaml` ("the more specific declaration wins", `doxyguard_db/declaration.py:312-326`).
5. **`--extra-input` / `--extra-exclude` CLI flags** — always appended on top of whatever roots/excludes tiers 1–4 produced (`doxyguard_db/cli.py:612-613`; merged in `doxyguard_db/doxygen.py:559-592`).
6. **The target's own Doxyfile `INPUT`** — used *only* as a base to be replaced. Under `--scope from-guard` it is always cleared (`replace_input=True`, `doxyguard_db/cli.py:614`, `doxyguard_db/doxygen.py:567-583`); its `ALIASES`/`PREDEFINED`/`STRIP_FROM_PATH` still apply regardless (`doxyguard_db/scope.py:9-16`).
7. **`--doxyfile` explicit path → discovered Doxyfile (repo root, then `docs/`, `doc/`) → synthesized minimal Doxyfile** — decides which Doxyfile text tiers 3–6 are layered onto; discovery deliberately refuses to guess among stray Doxyfiles elsewhere in the tree (`doxyguard_db/doxygen.py:189-234, 280-297`).
8. **`FILE_PATTERNS`** — unconditionally *forced* to doxygen's own built-in default extension list regardless of any declaration; a target's own `FILE_PATTERNS` can no longer veto files that scope has already admitted (`doxyguard_db/doxygen.py:60-154`). This is an independent override, not part of the roots/excludes precedence chain, but it still gates which files inside the chosen roots doxygen actually reads.
9. Inside whatever the whole-repo tier admits: **`.gitignore`** contents (parent repo and, separately, any nested git tree, since `git ls-files` doesn't see across submodule boundaries) are subtracted (`doxyguard_db/scope.py:220-229, 300-343`), and **dot-directories / `__pycache__` / `node_modules`** are always pruned (`doxyguard_db/scope.py:56, 124-126, 352-372`), bounded by a depth-16 walk guard (`doxyguard_db/scope.py:61, 365-369, 511-519`).

**What happens when a repo states nothing**

`derive_scope()` falls through every declared tier and returns `whole_repo_scope(root)` (`doxyguard_db/scope.py:190-191, 200-242`): the entire repository root becomes the single INPUT root, minus git-ignored paths (on both sides of any nested git tree) and the dot/cache directories — nothing else is trimmed. Nested git trees (submodules, stray clones) are **indexed, not excluded**; they get tagged as external afterward rather than cut from the file set (`doxyguard_db/scope.py:22-29, 200-209, 250-269`). If the repo also ships no Doxyfile at all, one is synthesized with an empty `INPUT` that then gets replaced by this whole-repo root (`doxyguard_db/doxygen.py:454-506`). This fallback is logged at **WARNING**, not INFO, specifically so an unchosen boundary is never mistaken for a chosen one (`doxyguard_db/scope.py:727-728`).

## Gaps

- I did not trace exactly how a "stated" `index_scope` document (tier 2 above) is populated end-to-end from the MCP server into `args`/`build_index(options=...)` — I confirmed it's consumed via `getattr(args, INDEX_SCOPE_SECTION, None)` (`doxyguard_db/cli.py:2051-2058` area) and merged before `_apply_scope`, but didn't locate the specific call site that sets `args.declare`/the stated dict from the MCP tool layer.
- I did not verify runtime behavior by actually running the pipeline against a live repo — this answer is based on static reading of `scope.py`, `doxygen.py`, `declaration.py`, and `cli.py`.
