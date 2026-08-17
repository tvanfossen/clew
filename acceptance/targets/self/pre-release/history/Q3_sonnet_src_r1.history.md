# Q3 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=cd ~/ddb-targets/self && find . -maxdepth 2 -iname "*doxyfile*" -o -iname "*doxygen*" | head -50
- **got:** ./doxyguard_db/doxygen.py ./tests/test_indexcache_doxygen_cache.py ./tests/test_doxyfile_refusal_messages.py ./.doxygen-guard.yaml

### 2. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/doxygen.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Doxygen invocation, output handling, and Doxyfile parsing. 3	 4	`run_doxygen` spawns the doxygen binary with our augmented Doxyfile, 5	streams its stdout to drive a Rich progress bar…

### 3. `Grep`
- **asked:** pattern=discover_doxyfile|describe_doxyfile_resolution|rejected_doxyfile_candidates, path=~/ddb-targets/self/doxyguard_db
- **got:** Found 11 files doxyguard_db/propose/registry.py doxyguard_db/preprocessor.py doxyguard_db/mcp_server/server.py doxyguard_db/mcp_server/state.py doxyguard_db/precommit.py doxyguard_db/kconfig.py doxyguard_db/init_command.…

### 4. `Grep`
- **asked:** pattern=discover_doxyfile|describe_doxyfile_resolution|rejected_doxyfile_candidates|DOXYFILE_", path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 115:    describe_doxyfile_resolution, 116:    discover_doxyfile, 121:    rejected_doxyfile_candidates, 1853:        found = Path(stated).resolve() if stated else discover_doxyfile(root) 2241:        doxyfile = discover_d…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 2225	    `_apply_scope` prepends derived roots, so the check only ever judges roots the 2226	    user actually named. 2227	 2228	    @brief Decide the Doxyfile and repo root for this build. 2229	    @return The resolved …

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 2190	    args.doxyfile = str(doxyfile) if doxyfile is not None else None 2191	    if scope is not None: 2192	        args.scope = scope 2193	    args.requirements = str(requirements) if requirements is not None else None…

**Reasoning.** I now have the complete picture to answer.

## Answer

**External tool driven:** `doxygen`. The program (`doxyguard-db`) looks for that tool's project configuration file, a `Doxyfile`.

### Where it looks

`discover_doxyfile()` (`doxyguard_db/doxygen.py:189-234`) checks exactly three locations, in order, and stops at the first hit:

1. `<repo>/Doxyfile` — repo root
2. `<repo>/docs/Doxyfile`
3. `<repo>/doc/Doxyfile`

(the trusted dirs are `_DOXYFILE_DIRS = ("docs", "doc")`, `doxyguard_db/doxygen.py:181`). It explicitly refuses to glob any other subdirectory — a prior version used `sorted(repo.g

---

## Final answer as submitted

I now have the complete picture to answer.

## Answer

**External tool driven:** `doxygen`. The program (`doxyguard-db`) looks for that tool's project configuration file, a `Doxyfile`.

### Where it looks

`discover_doxyfile()` (`doxyguard_db/doxygen.py:189-234`) checks exactly three locations, in order, and stops at the first hit:

1. `<repo>/Doxyfile` — repo root
2. `<repo>/docs/Doxyfile`
3. `<repo>/doc/Doxyfile`

(the trusted dirs are `_DOXYFILE_DIRS = ("docs", "doc")`, `doxyguard_db/doxygen.py:181`). It explicitly refuses to glob any other subdirectory — a prior version used `sorted(repo.glob("*/Doxyfile"))[0]` and that is documented as having picked a test fixture's Doxyfile to index the wrong project (`doxyguard_db/doxygen.py:200-212`).

`rejected_doxyfile_candidates()` (`doxyguard_db/doxygen.py:280-297`) separately globs `repo.glob("*/Doxyfile")` (one level deep, any subdirectory) minus the three trusted paths, purely to report strays it found but declined to use.

The CLI entry point (`cli.py:2241`, inside `_resolve_doxyfile_and_root`, `cli.py:2218`) calls `discover_doxyfile` only when no explicit `--doxyfile` was passed and `--repo-root` was given.

### What it does with files it finds but doesn't use

Stray Doxyfiles outside the three trusted locations are **found but never adopted** — `discover_doxyfile` still returns `None` for them (`doxyguard_db/doxygen.py:288-290`). The CLI logs a warning naming exactly where they were found and why they were rejected (`cli.py:2280-2285`, message built by `_msg_rejected`, `doxyguard_db/doxygen.py:362-374`), then proceeds to **synthesize** a minimal Doxyfile instead (`cli.py:2298`, `synthesize_doxyfile`, `doxyguard_db/doxygen.py:454-506`). Nothing about the stray file's content (ALIASES, PREDEFINED, filters) is read or merged in.

An explicit `--doxyfile <path>` that doesn't exist is also never silently substituted with a discovered one — if it's missing, that's the fatal `explicit_missing` case (`doxyguard_db/doxygen.py:245,322-323`); but if `--doxyfile` is combined with `--repo-root` and the path is invalid, the CLI additionally logs that the flag is being **ignored** in favor of whole-repo synthesis (`cli.py:2286-2297`).

### Every distinct outcome, and whether the build continues

Classified by `_doxyfile_situation()` / `describe_doxyfile_resolution()` (`doxyguard_db/doxygen.py:245-248, 307-326, 405-445`):

| Outcome | Condition | Build continues? |
|---|---|---|
| `explicit_missing` | `--doxyfile <path>` given but not on disk | **No** — fatal, `cli.py:2305`→`sys.exit(1)` (`_msg_explicit_missing`, `doxyguard_db/doxygen.py:333-341`) |
| `no_target` | neither `--doxyfile` nor `--repo-root` given | **No** — fatal, same exit path (`_msg_no_target`, `doxyguard_db/doxygen.py:348-355`) |
| `rejected` | repo searched, a Doxyfile found only in a non-trusted location | **Yes** — warning logged, a Doxyfile is synthesized (`doxyguard_db/doxygen.py:362-374`, `cli.py:2280-2298`) |
| `absent` | repo searched, genuinely ships no Doxyfile anywhere | **Yes** — treated as a supported configuration, synthesized (`_msg_absent`, `doxyguard_db/doxygen.py:381-389`) |
| found & used | Doxyfile present in one of the three trusted locations | **Yes** — used directly, `repo_root` set from it or `--repo-root` (`cli.py:2242-2243`) |

Two additional non-fatal branch outcomes worth noting, still under the `repo_root`-given path when no usable Doxyfile resolves (`cli.py:2244-2298`):
- if `--scope from-guard` and the repo's doxygen-guard config actually derives roots, a Doxyfile is synthesized against that declared scope (`cli.py:2249-2253`) — build continues;
- otherwise (no declared scope either) it falls to whole-repo synthesis (`cli.py:2254-2298`) — build continues, with the warning(s) described above.

So overall there are **5 distinct outcomes**: 2 fatal (`explicit_missing`, `no_target` — `sys.exit(1)`), and 3 that let the build proceed (found-and-used; `rejected`-then-synthesized; `absent`/no-declared-scope-then-synthesized, including the from-guard-derived-scope variant).

## Gaps

- I did not trace `mcp_server/state.py`'s own call to `discover_doxyfile` in detail (grep showed it's also a caller, alongside `init_command.py`, `precommit.py`, `kconfig.py`, `buildoptions.py`, `declaration.py`, `preprocessor.py`, `propose/registry.py`) — the CLI path (`cli.py:_resolve_doxyfile_and_root`) was confirmed as the fullest and canonical resolution logic per the source comments ("BOTH entry points need it" — `doxygen.py:194-198`), but I did not verify the MCP server path reproduces identical branching/outcomes rather than a subset.
- I did not inspect `init_command.py`'s `_check_indexable` reference (mentioned at `doxygen.py:223`) to confirm exactly how `doxyguard-db init` phrases these same outcomes.
