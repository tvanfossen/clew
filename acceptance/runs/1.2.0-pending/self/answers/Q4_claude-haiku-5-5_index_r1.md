**Short answer:** the caller list tells you which functions contain a resolved call to `git_argv`. It does not tell you where in those functions the call sits, what arguments it receives, or whether the call runs at all.

I checked this against `git_argv` (`clew/gitenv.py:89`), which the AGENTS.md names as the single git-argv choke point.

**What the reply holds for `git_argv`**

| Field | Value | What it actually claims |
|---|---|---|
| `callers` | 7 entries, each with name, file, `edge_class: call`, `confidence: resolved` | Seven functions contain a statically resolved call to it. |
| `callees` | empty | No indexed callee. The body only loops over a constant and builds a list, so this fits. |
| `threads` | `clew-first-build-` (pthread), `confidence: medium` | Reachability from a spawn point. It is not a call edge. |
| `requirements` | `REQ-DDB-CONFIG-001` | An annotation the function claims to satisfy. |
| `covering_tests` | `test_mqtt_dispatch_accepts_an_inline_document_not_only_a_path` | See below. This looks wrong. |
| `writes` / `reads` / `overrides` | empty | Present and empty, so they were measured as empty. |
| `callers_unresolved`, `context_undecidable` | 0 | No known gaps in the caller set. |

**What would make it wrong to read as a plain list of call sites**

1. **Callers are per function, not per site.** A grep finds 8 actual call sites: `clew/scope.py:865`, `clew/scope.py:1199`, `clew/guard/main.py:314`, `clew/guard/tags.py:56`, `clew/guard/git.py:72`, `clew/propose/notindexed.py:97`, plus the test file. The reply gives seven function names and no lines. Several sites in one function collapse into one entry.

2. **It says nothing about arguments.** `clew/guard/git.py:72` calls `git_argv(*cmd[1:])`, so the git subcommand comes from whatever `run_git` was handed. To learn what actually runs, you have to follow `run_git`'s own callers. Depth 1 only shows the immediate edge.

3. **Direct edges only.** Transitive reach needs `depth ≥ 2` with `direction: back`. A caller of a caller is not in this answer.

4. **Non-call references may be absent.** The edge class is `call`. A function passed as a value, stored in a table, or reached through `getattr` may not appear here. I did not test those cases; they are where I would look first for a missing edge.

5. **The covering test is a bad attribution.** `test_mqtt_dispatch_accepts_an_inline_document_not_only_a_path` (`tests/test_r1_richness.py:859`) tests MQTT dispatch loading an inline document. It has nothing to do with git argv. The test that does exercise `git_argv`, `tests/test_security_surface.py`, is missing from `covering_tests`. So requirement and coverage links are weaker evidence than the caller list and should not be read as proof of coverage.

6. **Different fields have different evidence.** `callers` is a static call edge. `threads` is spawn reachability at medium confidence. `requirements` and `covering_tests` are annotation links. They sit side by side in one reply and look equally authoritative.

**Rule of thumb:** treat the caller list as a starting set for grep and for `depth: 2` back-walks, and verify each site before relying on it. The reply is strongest on "who calls this" and weakest on "what does it receive" and "what covers it".