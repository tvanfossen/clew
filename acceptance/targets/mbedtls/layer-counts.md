<!-- SPDX-License-Identifier: MIT -->
# mbedtls — what the declared build measures, and where it still falls short

Measured 2026-08-13, `CLEW_BUILD_VERSION` 46, target `mbedtls-3.6.7` (068ff080), built
IN-PROCESS with `acceptance/targets/mbedtls/declaration.yaml`:

```
.venv/bin/python -m clew --output <target db> \
    --repo-root <mbedtls> --declare acceptance/targets/mbedtls/declaration.yaml --rebuild
```

**Not built through the MCP server, deliberately.** That process predates today's source, and a
stale server writes a stale index when refreshed through it — the `external` stage once vanished
that way while `status` reported perfectly healthy afterwards.

## The deltas

| layer | before | after | what moved it |
|---|---|---|---|
| `locks` | 1 | **10** | the declared `mbedtls_mutex_lock`/`_unlock` call pair |
| `lock_acquisitions` | 1 | **46** | same |
| `critical_section_calls` | 0 | **206** | the `releases` key, which the inline option route refused until #413 |
| `threads` | 1 | **2** | `_beginthread` joining `DEFAULT_SPAWN_PATTERNS` |

`critical_section_calls` going 0 → 206 is the direct evidence for the schema fix rather than an
argument about it: without a release token `_section_for` refuses the extent outright, so every
acquisition would have carried a NULL body and this table would have stayed empty.

## 45 of 48 for the DECLARED primitive, and the 46th row is a different primitive

**CORRECTED 2026-08-14. This section previously read "46 of 48, and the two that are missing are
the two `test_suite_psa_crypto.function` call sites". That was wrong in three ways at once, and
the third is the interesting one.**

Re-measured against the target and the built index:

| | count | how |
|---|---|---|
| `mbedtls_mutex_lock(` call sites | **48** | `git grep -n 'mbedtls_mutex_lock(' -- '*.c' '*.h' '*.function'` |
| …of those, in `tests/suites/*.function` | **3** | `test_suite_platform_threading.function:25`, `test_suite_psa_crypto.function:1347` and `:1422` |
| …therefore reachable to the AST layer | **45** | `harvest` routes grammars by extension and `.function` gets none |
| `lock_acquisitions` rows | **46** | the 45 above **plus one** `pthread_mutex_lock` site |

The three errors:

1. **It is 45, not 46**, for the declared primitive.
2. **THREE sites are unreachable, not two.** The claim named only the two in
   `test_suite_psa_crypto.function` and silently omitted
   `test_suite_platform_threading.function:25`.
3. **46 IS NOT A COUNT OF `mbedtls_mutex_lock` SITES AT ALL.** The 46th row is `mutex->mutex` in
   `library/threading.c` — the `pthread_mutex_lock(&mutex->mutex)` inside
   `threading_mutex_lock_pthread`, caught by the BUILT-IN POSIX pattern rather than by the
   declared one. So the old sentence compared a mixed-primitive numerator against a
   single-primitive denominator and read as a coverage ratio.

That third error is this project's own recurring shape: `call_edges` rows are not call
relationships, a `locks` row is not a mutex, and 46 acquisitions are not 46 `mbedtls_mutex_lock`
calls. A plausible ratio invites being quoted onward, which is exactly what a wrong one must not
be allowed to do.

Stated rather than rounded up: an arm that reports 48 from `git grep` is not wrong, an arm that
reports 45 harvested sites is not wrong either, and a mark demanding any single one of those
figures would punish a correct answer.

## 10 identities against 16 OBJECTS — the gap is the point, not a defect to hide

`evidence.md`'s census puts 16 mutex objects in this tree. The layer reports 10 identities, and
the arithmetic of the difference is exactly what `row_meaning` now discloses:

| ground truth | identities | how |
|---|---|---|
| 6 globals (5 named + `debug_mutex`) | **6** | one bare name each — exact, and `dossier` resolves every one to its type and declaration sites |
| 8 struct members | **3** | `cache->mutex`, `ctx->mutex`, `heap.mutex` — the six `ctx->mutex` users MERGE into one row |
| — | 1 | `mutex->mutex`, the pthread implementation's own parameter at `library/threading.c:81`; an artifact of the primitive, not one of the 16 |

So the member half under-counts 8 as 3, because identity is the operand SPELLING and six unrelated
struct types all spell it `ctx->mutex`. That is a false-sharing claim if quoted as an object count,
which is why the payload refuses to be read that way and instead names the four member spellings
so one grep completes the answer. Enumerating the objects needs a member-declaration harvest plus
receiver-type resolution — deferred, and named as deferred.

## Nothing here is a workaround for a missing feature

Declaring a repository's own conventions is the designed path. The defect was that nothing TOLD an
owner to declare it, which `status.diagnostics` now does — and the thread layer's counterpart to
that hint is still missing (#415).

The `preprocessor.predefined` half changes which SOURCE reaches the index, not what the index says
about it: `MBEDTLS_THREADING_C` is commented out in the shipped config, so without it doxygen
evaluates the whole threading layer away and the index would honestly report a library with no
locking. The source arm reads the same guarded code with no equivalent step, because `grep` does
not evaluate `#if`.
