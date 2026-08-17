# mbedtls — why each missed mark was missed

Every mark the 2026-08-13 n=1 index-arm spot check scored MISS, classified by driving the MCP
surface against the CURRENT index (build 47, declared) and recording what each call returns.

**The spot check itself was invalid** and the classification below is the reason it matters: it
ran against an index built WITHOUT the target's declaration, because `run_matrix.restore_target`
rebuilt before every cell and passed no `declare=` (fixed at `cbde404`). So a mark can be MISS in
that run and answerable now with no new capability at all.

| class | meaning | count |
|---|---|---|
| **REACHABILITY** | the data was already there, or is now; no build needed | 11 |
| **ROUTING** | the data exists in a layer the agent had no reason to ask about | 8 |
| **CAPABILITY** | no query returns it | 12 |
| **RUBRIC** | the mark is wrong, contradictory or resurrected — fix the key, not the tool | 4 |
| **PAYLOAD-FALSE** | the index's own reply points at the WRONG answer | 2 |
| **LIMITATION** | correct by design and not answerable; say so | 1 |
| answer-dependent | grading of how the answer phrased something | 1 |

Scored per cell: Q1 24/31, Q2 15/24, Q3 18/27, Q4 12/26.

---

## The two PAYLOAD-FALSE marks — highest severity

Q1 *"states it is OFF in the shipped default configuration"* and Q3 *"states that both are
commented out in the shipped default config"*.

Ground truth, `include/mbedtls/mbedtls_config.h`: `//#define MBEDTLS_THREADING_C` at `:3787` and
`//#define MBEDTLS_THREADING_PTHREAD` at `:2196`. **Both commented out.**

What the index replies. `search(corpus='config')` returns
`configured_macros: "MBEDTLS_THREADING_C" "MBEDTLS_THREADING_PTHREAD"`, and every one of the 154
`MBEDTLS_THREADING_C` gate rows carries `origin: "declared"`. An agent reading that concludes the
repository enables threading — the opposite of the graded fact.

The cause is our own acceptance declaration: `preprocessor.predefined` states both macros so
doxygen can reach the guarded bodies, and the payload reports them with no provenance. `origin`'s
docstring calls it *"the target's own declared preprocessor configuration"*, which is inaccurate
for a `--declare` document: the target declares nothing. `build_meta` does record
`preprocessor.source: declared`, but "declared" is ambiguous in exactly the wrong direction, and
the config-corpus reply does not carry it at all.

This is the same class as the two false-count rosters fixed at `1fad430` — a payload whose label
pushes toward a wrong claim — one layer over, and it is caused by the measurement's own setup.

**Fix shape (route, don't disclaim):** the config reply must say these macros were STATED FOR THIS
BUILD rather than read from the repository, and name where the repository's own default lives so
one grep settles it. `preprocessor.config_header` is already a declarable key;
`include/mbedtls/mbedtls_config.h` is the file.

---

## Cross-cutting defects this probe found, which no mark names

**The `config` corpus is unusable at this scale.** `search(corpus='config',
text='MBEDTLS_THREADING_C')` returned **2,149,463 characters** — all 12,096 `kconfig_gates` rows —
because inventory corpora ignore `text` by design. It also reported `found: false` for a symbol
whose name sits in `configured_macros` in the same reply. In a graded cell that is either a
budget-destroying reply or a bail-out, on the very axis under test. Two marks depend on this
corpus.

**No inventory corpus exists.** The five corpora are `symbols, prose, locks, threads, config`.
Q4 spent six `find … | wc` shell calls computing a per-directory rollup, and `coverage` reports
whole-repo totals only (`indexed_files: 443`, `substantive_files: 330`). Four Q4 marks need it.

**`scope.*` is unreachable for a named target.** `index(action='status')` refuses a `target` by
design (it reports the DERIVED target) and `stats(target=…)` omits the `scope` block, so the
`doxyfile_*` and `vendored_*` keys are reachable only from a server pinned to that repo with
`--repo`. The benchmark does pin it, so the graded run is unaffected — but a multi-target session
cannot reach them.

---

## Q4 — 14 misses (12/26)

Now reachable from `scope.*` after `cbde404` + `37f9e3e`, all absent from the graded index:

```
scope.doxyfile_path            doxygen/mbedtls.doxyfile
scope.doxyfile_file_patterns   *.h
scope.doxyfile_input           ../include, input, ../tests/include/alt-dummy
scope.vendored_declared        3rdparty
scope.vendored_roots           3rdparty
coverage.external_files        0        (with external_roots [])
```

| mark | class | evidence |
|---|---|---|
| finds the project's own documentation configuration | REACHABILITY | `doxyfile_path` |
| states its build covers HEADERS ONLY | REACHABILITY | `doxyfile_file_patterns = *.h` |
| reaches none of the implementation files | REACHABILITY | `input` is `../include` + `*.h` |
| the doc build cannot answer the second question | REACHABILITY | same two keys |
| `3rdparty/` is COMMITTED, not a submodule | REACHABILITY | `vendored_declared` **and** `external_files: 0` — declared vendored with no git tree is exactly this claim |
| identifies `include/` as the public interface | REACHABILITY | `doxyfile_input = ../include` for an API reference |
| an API reference documents the published CONTRACT | ROUTING | follows once the doxyfile keys are in hand |
| understanding what it DOES needs the implementations | ROUTING | same |
| identifies `programs/` as sample applications | CAPABILITY | no inventory corpus |
| identifies `tests/` as the test suite | CAPABILITY | no inventory corpus |
| `tests/` is the largest directory | CAPABILITY | no per-directory counts |
| largest contributor to the gap (`tests/`) | CAPABILITY | no per-directory counts |
| `framework/` is the one actual submodule | LIMITATION | its working tree is UNPOPULATED, so it owns zero indexed rows, and roots are reported only when they own at least one — correct by design (gh#335), and not answerable |
| says WHAT the figure counted | answer-dependent | — |

## Q3 — 9 misses (18/27)

| mark | class | evidence |
|---|---|---|
| names `debug_mutex` as what serialises output | REACHABILITY | `search(corpus='locks')` row: `debug_mutex`, `programs/ssl/ssl_pthread_server.c`, 1 acquisition |
| the only `mbedtls_mutex_lock` site outside `library/` and `tests/` | REACHABILITY | same single call — 9 of 10 rows are `library/`, one is `programs/` |
| both are commented out in the shipped default config | PAYLOAD-FALSE | see above |
| scopes the completeness claim to the tree (`framework/` unpopulated) | RUBRIC | this is the epistemic-habit mark the rubric's own re-aim table records as REPLACED; atomisation resurrected it. Delete. |
| mentions the stub `main` the guard compiles instead | CAPABILITY | no query returns an `#else` branch's body |
| the connection threads share state | CAPABILITY | needs argument dataflow into the entry |
| names the ONE shared `const mbedtls_ssl_config` | CAPABILITY | same |
| identifies stdout as shared | CAPABILITY | same |
| connects absent spawns to the library design | ROUTING | follows from the thread roster's own emptiness note |

One ROUTING fix serves several: the thread row carries `spawn_file` and `spawn_line: 277` but **no
`spawn_function`**, so `thread_create` — the function holding the spawn, whose body answers four of
these — is not named by anything the agent already has. Verified: `dossier('thread_create')`
returns the whole body, but nothing routes to that name.

## Q2 — 9 misses (15/24)

The workflow ran the replacement calls rather than predicting them. **Eight of Q2's ten fallbacks
were answerable by one index call the agent had no route to**, and in two cases the index BEATS
the grep it replaced:

- `dossier('MBEDTLS_ALLOW_PRIVATE_ACCESS')` lists all **three** definition sites including
  `programs/ssl/ssl_client2.c:8` and `ssl_server2.c:8`, which the agent's `--include`-filtered
  grep missed — and *"names at least one other opt-in site"* is a graded mark.
- `search(corpus='prose', text='structure fields private')` finds
  `docs/3.0-migration-guide.md`'s *"Most structure fields are now private"*, whose text contains
  no matching token for the literal grep that returned "No matches found" twice.

| mark | class | evidence |
|---|---|---|
| gets the DIRECTION right (prefixed is the default) | ROUTING | `dossier('MBEDTLS_PRIVATE')` already returns BOTH `#if` branches — rowid 3487 `private_##member` `ifndef`, rowid 12027 `member` `ifdef`. My planned "serve both branches" fix was unnecessary; nothing says the `macros[]` list is COMPLETE. |
| says WHICH consumer gets which | ROUTING | same payload |
| the struct is public so callers can ALLOCATE it | ROUTING | `dossier('mbedtls_aes_context')` returns members as `int MBEDTLS_PRIVATE(nr)` etc. |
| names another opt-in site | ROUTING | `dossier('MBEDTLS_ALLOW_PRIVATE_ACCESS')` — 3 sites |
| no access control, not C++ encapsulation | ROUTING | migration-guide prose |
| any TU can define the opt-in macro | ROUTING | the three sites + the two branches |
| ~860 of 884 uses in public headers | CAPABILITY | needs use-sites grouped by directory |
| dozens of files rather than a handful | CAPABILITY | same |
| a few uses outside `include/` | CAPABILITY | same |

Two further payload defects noted en route: a struct member's `kind` is reported `function`, and
`dossier` serves `brief` only — `memberdef.detaileddescription` holds the
`MBEDTLS_ALLOW_PRIVATE_ACCESS` deprecation warning and **no query returns it** (verified on
`mbedtls_ssl_handshake_step`, whose stored detail text contains the token while the dossier
returns one sentence).

## Q1 — 7 misses (24/31)

| mark | class | evidence |
|---|---|---|
| per-context `mutex` MEMBER as a second class | REACHABILITY | the locks `row_meaning` now names the four member expressions (`cache->mutex`, `ctx->mutex`, `heap.mutex`, `mutex->mutex`) — the routing fix from `1fad430` working |
| per-context mutexes are DISTINCT objects | REACHABILITY | same note: "one spelling reached from unrelated types is one row" |
| the file-static heap mutex | REACHABILITY | `heap.mutex` row present — and the INDEX is more precise than the mark, which calls it a file-static mutex when it is a member of the file-static `heap` |
| OFF in the shipped default configuration | PAYLOAD-FALSE | see above |
| FIVE named global mutexes | RUBRIC | `evidence.md`'s own census says six (`debug_mutex` is a true non-static global). An answer saying six is MORE correct and grades MISS. |
| the 52-vs-48 delta wording | RUBRIC | two of the three `threading.c` lines are definitions in mutually exclusive branches and one is an assignment; `evidence.md` gets this right and the mark does not |
| locates the pointer declarations in `include/mbedtls/threading.h` | RUBRIC/scoring | evidence is a FILE PATH ONLY, which `_symbols`/`_refs` cannot extract, so the mark went to the judge and scored MISS with quote NONE — while the answer's line 8 reads "declared `extern` in `include/mbedtls/threading.h:111-114`", the very line the judge quoted to award a different mark |

---

## CONTAMINATION — what these fixes teach the test, stated so the comparison stays honest

A fix that adds what the rubric grades contaminates that mark. Every item below is a genuine
defect fix AND a change to a graded surface, so the marks named here are **not comparable to the
2026-08-13 spot check**, and the honest baseline for them is that run's score.

| change | marks it teaches |
|---|---|
| `search.json` now describes the `files` corpus and its rollup | Q4's four directory marks — the tool description names the capability the agent previously replaced with `find \| wc` |
| `search.json` now tells the reader to read `macros_meaning` | Q1 and Q3's "OFF in the shipped default config" — the description points at the provenance field |
| `macros_meaning` names `mbedtls_config.h` as the route | the same two marks; the answer's location is now in the payload |
| `scope.doxyfile_*` reachable | Q4's five doc-build marks |
| `scope.vendored_*` reachable | Q4's "`3rdparty/` is committed, not a submodule" |
| `threads.spawn_function` | Q3's four `thread_create`-body marks |
| `dossier.detail` | Q2's two `MBEDTLS_ALLOW_PRIVATE_ACCESS` marks |

The three that are pure cost or correctness fixes and teach nothing — the `vote()` denominator,
the `_non_index_tools` sentinel, and the config corpus's 2.1 MB reply — are the only ones whose
before/after is directly comparable.

## What this scopes for the build phase

Ranked by marks recovered per unit of work, and **nothing here is built on a hypothesis the probe
did not test**:

1. **Config-reply provenance + a route to the shipped default** — fixes 2 PAYLOAD-FALSE marks,
   which are worse than misses because the tool argues for the wrong answer.
2. **A bounded `config` corpus that honours `text`** — 2.1MB replies are a cost defect on the
   measured axis.
3. **`spawn_function` on the thread row** — one field, names the function whose body answers four
   Q3 marks.
4. **An inventory corpus / per-directory rollup** — 4 Q4 marks and 3 Q2 marks, ~11 shell fallbacks.
5. **Serve `detaileddescription`** — 2 Q2 marks, stored and unserved.

My pre-probe plan ranked the directory rollup first and a "serve both `#if` branches" fix second.
The second does not exist — `dossier` already carries both branches — and the rollup is fourth.
Both corrections came from running the calls rather than reasoning about them.
