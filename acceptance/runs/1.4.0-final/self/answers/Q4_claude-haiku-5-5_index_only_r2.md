**What's in the answer.** For `git_argv` (clew/gitenv.py:89), the dossier returned:

- **`callers`**, grouped by file: six enclosing functions, including `_detect_git_version`, `run_git`, `_gitignored_paths` and a test, `test_the_disarmed_key_list_reaches_the_argv`. These are the functions that contain a call, not the call expressions.
- **`callees`**: empty. Calls to things clew doesn't index, such as stdlib or `subprocess`, aren't listed here.
- **Edge metadata**: `edge_class: call`, `source: ast`, `confidence: resolved`. Other symbols can carry `doxygen_sqlite` edges with `exact` confidence instead.
- **Context around the call**: the function's `threads` entry (here a spawned worker, `clew-first-build-`, with 72 members), `requirements` (REQ-DDB-CONFIG-001), `covering_tests`, `overrides`/`overridden_by`, `reads`/`writes`, and the verbatim `body`.

**What makes it wrong to read that as a list of call sites:**

1. **Callers are enclosing functions, one hop up.** They don't say where in the caller the call happens, how many times, or under which condition. Transitive callers need `depth ≥ 2` with `direction='back'`.
2. **Truncation is capped and visible only through `_limited`.** The default is 25 neighbours at depth 1 and 8 per hop deeper. A caller list that looks complete may be cut.
3. **Static edges miss indirect calls.** A function passed as a pointer is a variable, and the dossier says so: `mbedtls_mutex_lock` in the mbedtls example answers as a variable, not a function. Callbacks, dispatch tables and reflection also don't produce edges. An empty caller list therefore doesn't mean unused.
4. **Brace-initialised construction isn't modelled.** On `dossier` itself, `callers` came back empty, and the reply added a `callers_note` saying the name also resolves to a class and is probably a constructor. Ask for `kind='class'` before concluding that nothing constructs a type.
5. **Bare names can merge namesakes.** `dossier` resolves to two candidates, `QueryTools.dossier` and `query/subject.py:dossier`. A bare-name caller list can mix them, so pass `qualified` or `kind` to pick one identity.
6. **Some fields are reachability, not authorship.** `threads` means the function is reachable from a thread's entry through the graph, not that it is the entry. `covering_tests` is a coverage link and can be indirect; the `git_argv` entry is an MQTT dispatch test, which is a surprising match and needs checking before you rely on it.
7. **Edges can be stale.** `anchor_mismatch: true` means the lines changed since the last build, so the caller rows and body may not match the current source.

I checked two symbols, so these points come from what the replies showed, not from a full survey of clew's behaviour. Treat the caller list as a set of resolved static edges to start from. Confirm the call site and its conditions by reading the caller's body.