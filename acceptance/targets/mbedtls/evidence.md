<!-- SPDX-License-Identifier: MIT -->
# mbedtls — evidence behind the marks

**Rubric 1.0.0. Source facts at `mbedtls-3.6.7` = `068ff080b369adfac81509f9b57b2afabaf82dc5`,
read from a disposable pinned clone whose path is supplied at run time via `--target`. Nothing
here is graded.**

<!-- THE BUILDER'S PATH IS NOT RECORDED, and it used to be, twice in this file. This repo's
standing rule was written after a machine-layout disclosure forced the build-version-9 bump —
"store paths repo-relative, always; anything reachable over MCP is published" — and
`grade_matrix.anonymise` normalises machine paths out of every grade sidecar for exactly this
reason while the committed key carried one in plain sight. The COMMIT is the provenance; the local
path adds nothing a reader can use and everything an attacker can. -->


**RE-PINNED, AND THAT IS NOT COSMETIC.** The 0.5.0-era key was written against v3.6.2
(`107ea89…`), a commit that does **not exist** in the reference clone — it is grafted and
detached at 3.6.7 — so no figure in the old key could be checked against the tree the matrix
would actually run on. Everything below was re-measured with `git grep` / `git ls-files` at
068ff08. **Nothing here is derived from any artefact we build**; where a v3.6.2 figure and a
3.6.7 figure differ, the difference is recorded, because several of those differences turned a
mark FALSE rather than merely imprecise.

**SIX MARKS WERE RE-AIMED FROM AN EPISTEMIC HABIT TO A MBEDTLS FACT — Q3:6, Q3:8, Q5:7, Q6:8,
Q10:4, Q10:7.** All six used to grade caution (scope a completeness claim, state confidence, state
coverage, say what you could not determine, distinguish "has none" from "did not find any"), and
the served tool descriptions state those habits nearly verbatim to the index arm and not at all to
the source arm — so the marks measured which brief an arm had read. THE DESCRIPTIONS ARE UNCHANGED
and are not the defect; they are correct guidance. What moved is the marks. Each replacement is
recorded below under its question, with the command that measures it at 068ff08 and a line naming
what the mark used to grade. No mark count changed: 98 total, 89 graded, 9 fenced, and every
question keeps the number of marks it had. Q3, Q5, Q6 and Q10 now carry no contaminated mark;
eleven direct (Q0:1-2, 4-9, Q1:9, Q7:6-7) and one adjacent (Q0:3) remain and are still disclosed.

**The single biggest source of drift: `framework/`.** Between the two pins, mbedtls moved test
infrastructure into the `framework` submodule, which is UNPOPULATED here. `tests/src/helpers.c`
and `tests/src/threading_helpers.c` — which carried 19 mutex call sites, two run-time mutex
bindings, one `pthread_create` and one `MBEDTLS_ALLOW_PRIVATE_ACCESS` opt-in — are simply not in
this repository. Marks that offered those as creditable evidence were unanswerable by either arm.

---

# Q0 — Before you answer anything: is what you are reasoning from complete?

Q0 grades the AGENT'S BEHAVIOUR at bringup, not any property of a database, and it is the only
question in this rubric that refers to our tooling at all. The source fact it rests on is about
mbedtls:

```
Conditional compilation is the norm, not the exception, in this library.
  library/threading.c        entire body inside #if defined(MBEDTLS_THREADING_C)  (:18 .. :193)
  library/version.c          entire body inside #if defined(MBEDTLS_VERSION_C)    (:10 .. :32)
  include/mbedtls/mbedtls_config.h
      4,446 lines
        142 lines begin `#define MBEDTLS_`    — ON in the default build
        202 lines begin `//#define MBEDTLS_`  — present but commented OUT
  So the set of function bodies a reader can see AT ALL is a configuration outcome, and a
  default view of this repository under-covers it. That is the gap Q0 asks the agent to
  establish, state, and act on.
```

**Contaminated marks — disclose, do not average away.** EIGHT of Q0's nine marks are contaminated,
not four: **1, 2, 4, 5, 6, 7, 8 and 9**. The per-mark quotations are in `questions.md` under
"Contamination" and are not repeated here; what matters in this file is the correction. An earlier
draft named only 4-7 and attributed `status.json`'s "another operator of the same commit would not
get the same index" to them — that sentence is what **mark 8** grades ("does not present a widened
view as if it had been the default"), and marks 1 and 2 are handed `status.json`'s "CALL THIS
FIRST in a new session, and again before trusting an answer that surprises you … the index does
not rebuild itself", while mark 9 is handed `lock_roster.json`'s "is NOT evidence that the repo
has no mutexes" and `graph_stats.json`'s "Never report an absent layer as 'the repo has none'".

**Only Q0 mark 3 is close to unaided, and only partly.** The shared `provenance` text served by
`dossier` / `resolve_symbol` / `search` / `source` already says a recovered symbol's code "sits
behind a preprocessor guard the build did not satisfy" and that such an index "is incomplete about
that file" — so the MECHANISM is handed over and only the mbedtls-specific reading of it (that
nearly every function body in this library is guarded) is the arm's own work.

These marks are still worth grading — the question is whether the agent ACTS — but no result on
any of them may be reported as unaided.

**Q0 IS ACCEPTED AS IT STANDS, AND WHAT IT MEASURES IS "DID THE GUIDANCE LAND".** Eight of nine
marks being taught by the served descriptions is not a defect here: Q0 grades BRINGUP BEHAVIOUR,
and guidance that gets an agent to establish its basis before claiming things is the tool working
as designed. Report it on its own line, index arm only, as a measurement of whether the
instructions were followed — never as evidence of unaided understanding, and never inside the
per-question average. Contrast with the six marks re-aimed in this pass (Q3:6, Q3:8, Q5:7, Q6:8,
Q10:4, Q10:7): those sat inside the TWO-ARM comparison, where a habit taught to one arm only
measures which brief was read. Q0 has no source-arm counterpart, so there is nothing to compare
and nothing to contaminate.

**Q7 marks 6 and 7 are contaminated too, and losing that disclosure was the worse omission**,
because both were `[db-arm-only]` in the previous rubric version. Mark 6 ("describes how it made
sure its answer reflects the edit") is handed `status.json`'s "CALL THIS FIRST … the index does not
rebuild itself"; mark 7 ("reports what that cost, as a measured number") is handed
`build_or_refresh.json`'s "REPORTS WHAT IT COST … Quote those numbers as measurements; do not
estimate a refresh cost when this returns one". Unlike Q0, Q7 IS part of the two-arm comparison, so
this contamination lands on a graded surface both arms are scored on: Q7:6-7 are not comparable
across rubric versions.

---

# Q1 — Does this codebase use locking?

**The primitive is a FUNCTION POINTER — four of them, not one.**

```
include/mbedtls/threading.h:111-114
extern void (*mbedtls_mutex_init)(mbedtls_threading_mutex_t *mutex);
extern void (*mbedtls_mutex_free)(mbedtls_threading_mutex_t *mutex);
extern int (*mbedtls_mutex_lock)(mbedtls_threading_mutex_t *mutex);
extern int (*mbedtls_mutex_unlock)(mbedtls_threading_mutex_t *mutex);
```

That is deliberate: mbedtls is portable to any threading library, so the implementation is
pluggable at build time and replaceable at run time.

**THREE binding sites, all in `library/threading.c`** — so the honest answer is a SET of possible
implementations selected at build or run time:

```
library/threading.c:101-104   = threading_mutex_{init,free,lock,unlock}_pthread
                                under #if defined(MBEDTLS_THREADING_PTHREAD)  (:50)
library/threading.c:125-128   = threading_mutex_dummy / threading_mutex_fail
                                under #if defined(MBEDTLS_THREADING_ALT)      (:113)
                                — the stand-ins that REFUSE until a caller supplies its own
library/threading.c:138-141   = the caller's own functions, assigned by
                                mbedtls_threading_set_alt() (:133)
```

`threading_mutex_lock_pthread` is defined at `library/threading.c:75` and calls
`pthread_mutex_lock` at `:81`, so the chain from the pointer to a POSIX primitive is fully static
and complete.

**CHANGED SINCE v3.6.2:** the two run-time swaps in `tests/src/threading_helpers.c` are GONE —
that file moved into the `framework` submodule. There are three binding sites in this checkout,
not five, and no test-harness binding is findable by either arm.

**AND THE WHOLE LAYER IS OFF BY DEFAULT.** All three gating macros are commented out in the
shipped default configuration:

```
include/mbedtls/mbedtls_config.h:3787   //#define MBEDTLS_THREADING_C
include/mbedtls/mbedtls_config.h:2196   //#define MBEDTLS_THREADING_PTHREAD
include/mbedtls/mbedtls_config.h:2185   //#define MBEDTLS_THREADING_ALT
```

`library/threading.c`'s entire body sits inside `#if defined(MBEDTLS_THREADING_C)` (`:18`,
`:193`), as does the declaration block in `threading.h`. So "does mbedtls lock?" has a
build-dependent answer: the code is thread-SAFE by construction when threading is enabled, and
compiles the locking away when it is not.

**Finally, the mutexes are not one lock.** Five named globals live in `library/threading.c`
guarding independent state, and seven public context structs carry their own per-instance mutex,
so the number of distinct mutexes is bounded only by the number of live contexts.

### Verified facts — SOURCE at mbedtls-3.6.7 (the arbiter)

```
RE-MEASURED 2026-08-11 at 068ff08, WHOLE TREE, with `git grep -n <sym> | wc -l` and
`git grep -l <sym> | wc -l`. An earlier draft of this table reported 45 lock occurrences in 14
files "1 in programs/, the rest under library/" — it had silently omitted tests/suites/ and the
declaration, so it UNDERSTATED the tree and would have penalised a grep arm that simply reported
what one command prints. Corrected figures, with the non-call lines named:

mbedtls_mutex_lock    52 lines in 18 files    of which 1 is the declaration
                                              (include/mbedtls/threading.h:113) and 3 are the
                                              pointer definitions/assignment in
                                              library/threading.c:103,:127,:140
                                              => 48 CALL SITES in 16 files
                                                 44 in 13 files under library/
                                                  1 programs/ssl/ssl_pthread_server.c:73
                                                  1 tests/suites/test_suite_platform_threading
                                                       .function:25
                                                  2 tests/suites/test_suite_psa_crypto
                                                       .function:1347,:1422
                                              (v3.6.2 read 61 in 15 files; the 19 in
                                               tests/src/helpers.c left with framework/)
mbedtls_mutex_unlock  60 lines in 18 files    1 declaration + 3 in library/threading.c
                                              => 56 call sites in 16 files, 50 under library/,
                                                 1 in programs/, 5 in tests/suites/
mbedtls_mutex_init    23 lines in 15 files    (one of them is ChangeLog prose, not code;
                                              8 of the rest are in library/threading.c)
mbedtls_mutex_free    21 lines in 14 files    (one ChangeLog line; 8 in library/threading.c)
declarations          include/mbedtls/threading.h:111-114, four extern function pointers,
                      inside #if defined(MBEDTLS_THREADING_C)
bindings              threading.c:101-104 pthread · :125-128 ALT stand-ins · :138-141 set_alt
backend chain         mbedtls_mutex_lock -> threading_mutex_lock_pthread (threading.c:75)
                                         -> pthread_mutex_lock (threading.c:81)
gate                  MBEDTLS_THREADING_C, _PTHREAD and _ALT all commented out by default
named global mutexes  5, defined at library/threading.c:182-190 and declared at
                      threading.h:120,:130,:144,:151,:158 — readdir, gmtime, key_slot,
                      psa_globaldata, psa_rngdata; each is itself behind its own #if
per-context mutexes   MBEDTLS_PRIVATE(mutex) members in 7 public headers — entropy.h, rsa.h,
                      ssl_cache.h, ctr_drbg.h, hmac_drbg.h, ssl_cookie.h, ssl_ticket.h —
                      plus the file-static heap struct in library/memory_buffer_alloc.c
busiest call site     library/psa_crypto.c, 19 lock occurrences
example site          library/psa_crypto_slot_management.c, 5 lock occurrences,
                      mbedtls_mutex_lock(&mbedtls_threading_key_slot_mutex)
per-file lock counts  `git grep -c mbedtls_mutex_lock`, every file it names:
                      library/psa_crypto.c 19 · library/psa_crypto_slot_management.c 5 ·
                      library/entropy.c 4 · library/ssl_cache.c 3 · library/threading.c 3 (the
                      pointer definitions/assignment, NOT calls) · library/ssl_ticket.c 2 ·
                      library/ssl_cookie.c 2 · library/rsa.c 2 ·
                      library/memory_buffer_alloc.c 2 · library/x509_crt.c 1 ·
                      library/psa_crypto_random.c 1 · library/platform_util.c 1 ·
                      library/hmac_drbg.c 1 · library/ctr_drbg.c 1 ·
                      include/mbedtls/threading.h 1 (the declaration) ·
                      programs/ssl/ssl_pthread_server.c 1 ·
                      tests/suites/test_suite_platform_threading.function 1 ·
                      tests/suites/test_suite_psa_crypto.function 2
                      = 52 lines, 18 files, 48 of the lines being calls
in-tree test call sites  THREE, and they are creditable evidence: the suites are .function
                      templates rather than .c, so they are compiled only after the generators
                      in the framework submodule run — but the SOURCE is in this checkout and
                      both arms can read it.
```

### THE MUTEX OBJECT CENSUS — 16, and how three of them were missed three times

Added 2026-08-13. The block above counts CALL SITES correctly and never states the number of
mutex OBJECTS, which is the figure Q1's enumeration marks turn on and the figure the index gets
wrong. Enumerated with `git grep -n mbedtls_threading_mutex_t` over ALL tracked files — no
extension filter, no path prefix:

```
6 GLOBALS
  5 named, extern in include/mbedtls/threading.h:120,:130,:144,:151,:158, defined
    library/threading.c:182,:185,:188,:189,:190 — readdir, gmtime, key_slot,
    psa_globaldata, psa_rngdata; each behind its own #if
  1 debug_mutex, programs/ssl/ssl_pthread_server.c:65 — a global OUTSIDE library/,
    and the object taken at that file's call site (:73)
8 STRUCT MEMBERS
  7 MBEDTLS_PRIVATE(mutex) in public headers — ctr_drbg.h:228, entropy.h:114,
    hmac_drbg.h:100, rsa.h:120, ssl_cache.h:72, ssl_cookie.h:59, ssl_ticket.h:82
  1 the file-static heap struct, library/memory_buffer_alloc.c:63
2 IN THE TEST SUITES
  tests/suites/test_suite_platform_threading.function:19   mutex
  tests/suites/test_suite_psa_crypto.function:1329          MBEDTLS_PRIVATE(key_loaded_mutex)
  — the objects behind the three in-tree test call sites already named above. Same
    creditable-evidence argument: .function templates, but the SOURCE is in this checkout.
= 16 OBJECTS
```

**THE METHOD FINDING, and it is worth more than the number.** This count was wrong twice before
it was right, and both times the tool was fully capable while the QUERY was not:

| attempt | figure | why it was wrong |
|---|---|---|
| 1 | 12 | grep restricted to `include/` — missed `library/memory_buffer_alloc.c` and `programs/` |
| 2 | 14 | `grep --include=*.c --include=*.h` — no extension matches `.function`, so both test-suite objects were invisible |
| 3 | **16** | `git grep`, all tracked files, no filter |

An independent agent reading the same source reported 13, by a third route.

So: **"no rows" is a claim about the DETECTOR, and "these rows" is a claim about your QUERY.**
The standing lesson had only the first half. A grep is not blind here — a narrow invocation is,
and it fails silently and plausibly, returning a tidy count that looks like an answer.

**Why this matters for the grading, not just for tidiness.** Ground truth derived from one grep
cannot ever mark the SOURCE arm incomplete, and cannot credit the index for finding something a
grep missed — the rubric would be biased toward the source arm by construction. Every count here
must therefore be triangulated: an exhaustive sweep, the index's answer, and a hand read, with
disagreements recorded rather than reconciled away. A disagreement is the finding: it says
whether a miss is a CAPABILITY limit or a REACH limit, and those are graded differently.

**What the index says about the same thing, recorded as a disagreement.** `search(corpus="locks")`
returns ONE row — `mutex->mutex`, `scope: unknown`, `identity_confidence: low` — and its
`row_meaning` instructs the reader to *"Quote origin.first_party as the repository's mutex count"*,
i.e. to state 1 against a true 16. That is a capability limit, not a reach limit: the default lock
patterns do not name `mbedtls_mutex_lock`, and the primitive is a function POINTER so the fnptr
layer resolves each call to `threading_mutex_lock_pthread` and the pointer's own name never appears
as a callee. Six of the objects ARE reachable today through the variable layer (`dossier` returns
`debug_mutex` and `mbedtls_threading_readdir_mutex` with their type and declaration sites); the
eight struct members are not modelled at all.

**Contaminated mark — Q1 mark 9.** `lock_roster.json` was edited after the previous run to say
that a repository's own mutex count must be quoted rather than a total, and it names a 52-of-97
split as the reason. Mark 9 grades exactly the distinction between the mutex OBJECTS and the
primitive / the row count. The index arm is handed that distinction in prose; the source arm is
not. Report mark 9 as contaminated.

# Q2 — The same struct member has two different names. Which, why, and who gets which?

### Verified facts — SOURCE at mbedtls-3.6.7

```
include/mbedtls/private_access.h:14-18    the whole mechanism, 5 lines of it:
    #ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
    #define MBEDTLS_PRIVATE(member) private_##member
    #else
    #define MBEDTLS_PRIVATE(member) member
    #endif

MBEDTLS_PRIVATE( uses   891 in 66 files   872 of them under include/
                                          (v3.6.2 read 876 in 67 files / 856)
busiest headers         include/mbedtls/ssl.h        209
                        include/psa/crypto_struct.h   68
                        include/mbedtls/cipher.h      50
                        include/psa/crypto_se_driver.h 45
                        include/psa/crypto_builtin_composites.h 41
                        include/psa/crypto_extra.h    39
                        include/mbedtls/x509_crt.h    35
                        include/psa/crypto_builtin_key_derivation.h 32

MBEDTLS_ALLOW_PRIVATE_ACCESS is defined in exactly 3 places besides the macro's own header:
    library/common.h:132                     — so EVERY library translation unit sees the
                                               plain names
    programs/ssl/ssl_client2.c:8             — a sample program
    programs/ssl/ssl_server2.c:8             — a sample program
  CHANGED SINCE v3.6.2: the four opt-ins under tests/ (test/helpers.h,
  test/threading_helpers.h, bignum_helpers.c) went into the framework submodule. "The test
  harness opts in" is NO LONGER FINDABLE in this checkout, so Q2 mark 6 now names the sample
  programs only.

what it is NOT          not a visibility control, not a compiler attribute, not a build
                        option in mbedtls_config.h. It is token pasting, and the entire
                        enforcement is that an application that does not opt in cannot
                        spell the member's name.
```

# Q3 — What runs concurrently here?

### Verified facts — SOURCE at mbedtls-3.6.7

```
spawn sites            2, in 2 files, NEITHER of them under library/
  programs/ssl/ssl_pthread_server.c:277   pthread_create(&threads[i].thread, NULL,
                                          handle_ssl_connection, ...)
                                          one thread per accepted connection, running the
                                          whole TLS handshake and echo exchange for that client
  programs/test/benchmark.c:430           _beginthread(TimerProc, 0, NULL) — Windows only,
                                          a benchmark timer, not part of the library
library/                                  NO thread creation of any kind, by any primitive

MARK 6 — THE SPAWN SITE IS ITSELF CONDITIONALLY COMPILED, AND OFF BY DEFAULT
  Re-measured 2026-08-11 at 068ff08:
    git grep -nE 'MBEDTLS_THREADING_PTHREAD' -- programs/ssl/ssl_pthread_server.c
  programs/ssl/ssl_pthread_server.c:24
      #elif !defined(MBEDTLS_THREADING_C) || !defined(MBEDTLS_THREADING_PTHREAD)
                        :25-29  int main(void) { mbedtls_printf("MBEDTLS_THREADING_PTHREAD not
                                defined.\n"); mbedtls_exit(0); }
                        :30     #else   <- the real program, including the pthread_create at :277
  and BOTH gating macros are commented out in the shipped configuration (see Q1):
      include/mbedtls/mbedtls_config.h:3787   //#define MBEDTLS_THREADING_C
      include/mbedtls/mbedtls_config.h:2196   //#define MBEDTLS_THREADING_PTHREAD
  So a DEFAULT build of this repository creates no threads at all: the library never did, and the
  one POSIX spawn site compiles to a stub that prints and exits. This is the fact mark 6 grades.
  It overlaps Q1 mark 8 in mechanism (conditional compilation of the threading layer) and not in
  subject: Q1:8 is about the LOCK primitive, this is about the SPAWN. Different cells, so no leak.

MARK 8 — WHAT THE CONNECTION THREADS SHARE
  Re-measured 2026-08-11 at 068ff08:
    git grep -nE 'MAX_NUM_THREADS|debug_mutex|my_mutexed_debug|mbedtls_ssl_context ssl;|const mbedtls_ssl_config \*config' -- programs/ssl/ssl_pthread_server.c
  programs/ssl/ssl_pthread_server.c:63    #define MAX_NUM_THREADS 5   — at most five at a time,
                                          slots reused (:253 scan, :266 refusal)
                        :83-87  typedef struct { mbedtls_net_context client_fd; int
                                thread_complete; const mbedtls_ssl_config *config; } thread_info_t
                                — ONE shared, const config pointer handed to every thread
                        :105    mbedtls_ssl_context ssl;   — inside handle_ssl_connection (:98),
                                i.e. one context PER THREAD, on that thread's stack
                        :65     mbedtls_threading_mutex_t debug_mutex;
                        :67     my_mutexed_debug(), :73 lock / :80 unlock around the fprintf
                        :406    mbedtls_ssl_conf_dbg(&conf, my_mutexed_debug, stdout)
                        :321 init / :483 free of debug_mutex
  The shared resource that needs a lock here is STDOUT, not any mbedtls object — which is why
  :73 is the ONE mbedtls_mutex_lock call site outside library/ and tests/ (Q1's table).

CHANGED SINCE v3.6.2 — CONTEXT, NO LONGER GRADED BY ANY MARK:
  tests/src/threading_helpers.c:25 held a third spawn — pthread_create inside
  threading_thread_create_pthread, whose entry is a PARAMETER. That file is now in the
  framework submodule, which is NOT POPULATED here (`git submodule status` reports
  `-dde0c4a0e448a0552f18817dcea633bb851fd288 framework`; the leading '-' means uninitialised).
  tests/src/ in this checkout holds only certs.c, psa_test_wrappers.c and test_helpers/.
  So "the tests do not spawn threads" is TRUE of the tree and FALSE of the project. THAT USED TO
  BE MARK 6, and it was re-aimed: grading whether an answer SCOPES a completeness claim grades an
  epistemic habit the served tool descriptions hand to one arm and not the other. Mark 6 now
  grades the guard above. The submodule's absence is still a graded fact — in Q8 mark 1, where it
  is the concrete answer to a concrete question rather than a caution attached to another one.
```

# Q4 — What in this repository is mbedtls's own code, and what is not?

### Verified facts — SOURCE at mbedtls-3.6.7

```
tracked files          949 in all; 431 of them are .c or .h
                       (v3.6.2 read 1,023 and 480 — the difference is framework/'s departure)

  tests/       310 files              the largest directory in the repository
  library/     177 files             109 *.c implementations — the library
  programs/    123 files              sample applications
  include/      99 files ( 97 .h)     the public interface: include/mbedtls/ 74 .h
                                                            include/psa/     23 .h
  visualc/      61 files              generated Visual Studio project files
  scripts/      43 files              build and generation tooling
  docs/         42 files              prose
  3rdparty/     38 files              NOT mbedtls's code — see below
  (root)        23 files
  configs/      14 files              alternative complete configurations
  doxygen/       8 files              the documentation build plus 7 doc-only headers
  pkgconfig/     6 files
  framework/     1 tracked entry      the gitlink itself; see Q8

3rdparty/, in its own words
  3rdparty/everest    Project Everest — a formally verified Curve25519 implementation whose
                      C "is automatically derived from the (verified) original implementation
                      ... in the F* language by KreMLin" (3rdparty/everest/README.md)
  3rdparty/p256-m     files that "originate from the p256-m GitHub repository ... authored by
                      Manuel Pégourié-Gonnard", and "p256-m files in the Mbed TLS repo will
                      not be updated regularly, so they may not have fixes and improvements
                      present in the upstream project" (3rdparty/p256-m/README.md)

the project's own documentation build — doxygen/mbedtls.doxyfile
  :1   PROJECT_NAME    = "Mbed TLS v3.6.7"
  :9   INPUT           = ../include input ../tests/include/alt-dummy
  :10  FILE_PATTERNS   = *.h
  :11  RECURSIVE       = YES
  :5-7 EXTRACT_ALL / EXTRACT_PRIVATE / EXTRACT_STATIC = YES
  -> headers only. NONE of the 109 library/*.c implementations, by declaration.
     `doxygen/input/` is 7 doc-only headers (doc_mainpage.h, doc_ssltls.h, doc_x509.h,
     doc_encdec.h, doc_hashing.h, doc_rng.h, doc_tcpip.h) that exist solely to carry prose
     for that build.
```

# Q5 — Orient in an unseen codebase

### Verified facts — SOURCE at mbedtls-3.6.7

```
main definitions      RE-MEASURED 2026-08-11 at 068ff08. An earlier draft of this line read
                      "60 FILES, 118 textual definitions, ALL under programs/. No main anywhere
                      under library/, include/ or tests/" — the last sentence is FALSE and the
                      counts were both low.
                        git grep -lE '^int main'      -> 62 files: 61 under programs/,
                                                         ONE under tests/ —
                                                         tests/suites/main_test.function:241
                        git grep -nE '^int main'      -> 120 lines: 119 programs/, 1 tests/
                        git grep -lE 'int +main *\('  -> 63 files: 62 programs/, 1 tests/
                      (v3.6.2 read 64 files / 121 definitions.)
                      The file count and the line count differ because several sample programs
                      carry a stub main under one #if and the real one under another — itself an
                      instance of the conditional compilation Q1 and Q11 turn on.
                      The tests/ hit is the GENERATOR TEMPLATE from which every test binary's
                      main is produced: framework/scripts/generate_test_code.py takes
                      suites/main_test.function as its `-t` template
                      (tests/CMakeLists.txt:312, tests/Makefile:231). It is real, tracked, and
                      readable by both arms, so an answer that names it is right rather than
                      wrong — which is why the mark now says "almost all under programs/".
                      NO main under library/ or include/: `git grep -nE '^int main' --
                      library/ include/` returns nothing.
public interface      include/mbedtls/ (74 .h) + include/psa/ (23 .h)
implementations       library/*.c (109)
DIRECTORY SHAPE       MARK 7, re-measured 2026-08-11 at 068ff08:
                        git ls-files library/ | grep -c '^library/.*/'   -> 0
                        git ls-files 'library/*.c' | wc -l              -> 109
                        git ls-files 'library/psa_crypto*.c' | wc -l    -> 15
                        git ls-files 'library/ssl*.c' | wc -l           -> 14
                        git ls-files 'library/x509*.c' | wc -l          ->  8
                      library/ is FLAT: 177 tracked entries, NOT ONE of them in a subdirectory.
                      The de facto module grouping is the filename prefix, so an answer that
                      describes library/ as organised into subsystems on disk has invented it.
                      include/ is the opposite shape and stops at depth two:
                        git ls-files include/ | cut -d/ -f2 | sort -u
                          -> .gitignore, CMakeLists.txt, mbedtls, psa   (two subdirectories)
                        git ls-files include/ | grep -c '^include/[^/]*/[^/]*/'  -> 0
                      MARK 7 PREVIOUSLY GRADED "states coverage honestly", an epistemic habit the
                      served descriptions hand to one arm only; it now grades this shape. Naming
                      either half — flat library/, or include/'s two namespaces — earns it.
what it is            README.md:4 — "Mbed TLS is a C library that implements cryptographic
                      primitives (including the PSA Cryptography API), X.509 certificate
                      manipulation and the SSL/TLS and DTLS protocols. Its small code
                      footprint makes it suitable for embedded systems."
prose worth finding   docs/ carries a 3.0 migration guide, a PSA transition guide, a
                      use-psa-crypto guide, and docs/architecture/ (including
                      psa-thread-safety/psa-thread-safety.md, which is directly relevant
                      to Q1)
```

# Q6 — Find a capability by concept, not by name

### Verified facts — SOURCE at mbedtls-3.6.7

```
public entry points, all in library/x509_crt.c
  :3159  mbedtls_x509_crt_verify              — the simple form
  :3176  mbedtls_x509_crt_verify_with_profile — takes a policy profile
  :3195  mbedtls_x509_crt_verify_with_ca_cb   — trusted signers supplied by callback
  :3210  mbedtls_x509_crt_verify_restartable  — the ECC-restartable form
  :3166-3171  the simple form supplies &mbedtls_x509_crt_profile_default and delegates

the real body           x509_crt_verify_restartable_ca_cb (:3063), whose own comment at
                        :3046-3053 states the order:
                          - checks the requested CN (if any)
                          - checks the type and size of the EE cert's key
                          - builds and verifies the chain
                          - then calls the callback and merges the flags

per-step helpers        x509_crt_verify_chain            :2511
                        x509_crt_find_parent             :2382
                        x509_crt_find_parent_in          :2259
                        x509_crt_check_signature         :2129
                        x509_crt_check_ee_locally_trusted :2448
                        x509_crt_verifycrl               :2015   (revocation)
                        x509_crt_merge_flags_with_cb     :3019

the OUTPUT is FLAGS     a uint32_t of MBEDTLS_X509_BADCERT_* bits accumulated per certificate
                        and merged over the chain — MBEDTLS_X509_BADCERT_CN_MISMATCH is set
                        at :3013 — so a caller can tell an expired certificate from an
                        untrusted one. mbedtls_x509_crt_verify_info (:1907) renders them.

REVOCATION — MARK 8     Re-measured 2026-08-11 at 068ff08:
                          git grep -nE 'x509_crt_verifycrl|BADCERT_REVOKED|MBEDTLS_X509_CRL_PARSE_C' -- library/x509_crt.c
                        library/x509_crt.c:1991  #if defined(MBEDTLS_X509_CRL_PARSE_C)
                                           :2015  static int x509_crt_verifycrl(crt, ca, ca_crl,
                                                  profile, now)
                                           :2115  flags |= MBEDTLS_X509_BADCERT_REVOKED
                                           :2124  #endif /* MBEDTLS_X509_CRL_PARSE_C */
                                           :2678-2683 called PER CHAIN LINK from
                                                  x509_crt_verify_chain (:2511):
                                                    *flags |= x509_crt_verifycrl(child, parent,
                                                              ca_crl, profile, &now);   (:2680)
                                                  with `(void) ca_crl;` in the #else — so with
                                                  the option off, revocation is not checked
                        MARK 8 PREVIOUSLY GRADED "states what it could not determine", a habit the
                        served descriptions teach one arm and not the other; it now grades this.
                        Chain building plus the per-certificate checks is NOT the whole of
                        verification: the CRL step is a distinct mechanism AND a separate
                        compile-time option.

the POLICY is DATA      four profiles ship, all in library/x509_crt.c:
                        _default :89 · _next :117 · _suiteb :142 · _none :163
                        each names allowed message digests, allowed public-key types,
                        allowed curves and a minimum RSA key size
```

# Q7 — Edit the codebase, then answer about what you wrote

### Verified facts — SOURCE at mbedtls-3.6.7

```
library/version.c        32 lines, defines exactly 3 functions, all inside
                         #if defined(MBEDTLS_VERSION_C) (:10 .. :32):
                           :15  mbedtls_version_get_number
                           :20  mbedtls_version_get_string
                           :26  mbedtls_version_get_string_full
                         small, stable, and a clean place to add a probe
callers of a new symbol  0 — nothing can call a function that was just written

OPERATOR NOTE, not a mark: this question MUTATES the target, so the sweep needs the per-cell
restore, and `run_matrix.restore_target_preflight` refuses to start unless the target carries a
`.acceptance-disposable` marker file. STATUS RE-CHECKED 2026-08-11: the reference clone DOES now
carry one (994 bytes, untracked, `?? .acceptance-disposable` in that clone's `git status`), so the
preflight will pass.
An earlier draft of this note said the clone did NOT carry one; that was true when written and is
false now — the marker was added by the operator in the meantime. Restore therefore runs
`git checkout -- .` + `git clean -fd -e .acceptance-disposable` in that clone before EVERY cell,
which is the intended behaviour for a disposable pinned clone and destroys anything uncommitted
left in it. The marker is untracked, and `run_matrix.restore_target` excludes it from the clean
explicitly (`run_matrix.py:546`) — without that the first cell would delete the operator's own
opt-in and every later cell would refuse. Checked, not assumed.
```

# Q8 — What is missing from this checkout, and what in it was not written by hand?

### Verified facts — SOURCE at mbedtls-3.6.7

```
framework/ IS A SUBMODULE AND IS NOT POPULATED HERE
  .gitmodules            path = framework, url = .../Mbed-TLS/mbedtls-framework
  git submodule status   -dde0c4a0e448a0552f18817dcea633bb851fd288 framework
                         the leading '-' means uninitialised; the directory is empty
  CMakeLists.txt:318-323 FATAL_ERROR "... CMakeLists.txt not found (and does appear to be a
                         git checkout). Run `git submodule update --init` from the source tree
                         to fetch the submodule contents."  — then :325 add_subdirectory(framework)
  Makefile:5-21          the same refusal for framework/exported.make, but ONLY for targets
                         other than `lib` / `library/%`: `make lib` builds the LIBRARY
                         without the submodule; everything else stops
  what lives in it       the test generators AND the shared test sources —
                         CMakeLists.txt:352-353 globs framework/tests/src/*.c, and
                         :366-388 invoke framework/scripts/generate_psa_wrappers.py and
                         generate_test_keys.py

THE TEST SUITES DO NOT EXIST AS C
  tests/suites/          94 *.function files, 140 *.data files, ZERO *.c
                         the compilable test programs are produced at build time from those

GENERATED C THAT IS TRACKED (present in the tree, still not hand-written)
  library/psa_crypto_driver_wrappers.h    ~108 KB   scripts/generate_driver_wrappers.py
                                          banner: "Warning: This file is now auto-generated."
  library/ssl_debug_helpers_generated.c             scripts/generate_ssl_debug_helpers.py
  programs/psa/psa_constant_names_generated.c       scripts/generate_psa_constants.py
  tests/include/test/test_keys.h                    framework/scripts/... (see above)
  tests/src/psa_test_wrappers.c, tests/include/test/psa_test_wrappers.h
  also scripts/generate_errors.pl, generate_features.pl, generate_query_config.pl,
       generate_visualc_files.pl, generate_tls_handshake_tests.py

  programs/test/query_config.c            5,305 lines   scripts/generate_query_config.pl
                                          from the template scripts/data_files/query_config.fmt
    CORRECTION, 2026-08-11. An earlier draft of this line said this file "is NO LONGER TRACKED —
    it is now produced at build time". THAT IS FALSE at 068ff08 and a grader checking it would
    have been misled: `git ls-files --error-unmatch programs/test/query_config.c` succeeds, and
    the file was last touched by 068ff08 itself. What is true is that it is BOTH tracked AND
    regenerable, which is why it is a good example rather than a bad one:
      programs/Makefile:135      GENERATED_FILES = psa/psa_constant_names_generated.c
                                                   test/query_config.c
      programs/Makefile:146-156  regenerates it IN THE SOURCE TREE from the .fmt template
      programs/test/CMakeLists.txt:48-57  generates a SEPARATE copy into the build directory
    and it carries NO "auto-generated" banner at all — `grep -i generat` on it matches only
    PSA macro names — so for THIS file the only tell is the build rule naming it as an output
    and the .fmt template it is cut from. Its header moved: query_config.h is now
    $(FRAMEWORK)/tests/programs/query_config.h (programs/Makefile:304), i.e. inside the
    unpopulated submodule. Both categories — generated-and-committed and generated-at-build —
    still exist, which is what mark 7 grades, and this one file is in both.

HOW A READER CAN TELL
  17 tracked .c/.h files carry an "automatically generated" / "auto-generated" / "DO NOT EDIT"
  style banner — re-measured 2026-08-11 with
    git grep -lEi 'automatically generated|auto-generated|autogenerated|DO NOT EDIT' -- '*.c' '*.h'
  which lists library/psa_crypto_driver_wrappers.h, library/ssl_debug_helpers_generated.c,
  programs/psa/psa_constant_names_generated.c, tests/include/test/test_keys.h,
  tests/src/psa_test_wrappers.c and 12 more. A `_generated` suffix in the filename and a build
  rule naming the file as an OUTPUT are the other two tells, and they are not the same set:
  programs/test/query_config.c is generated and is NOT in the 17, because it carries no banner
  (see above). An answer naming any one of the three tells has earned mark 6.
```

# Q9 — This library ships two public cryptography APIs. Which, and which should new code use?

### Verified facts — SOURCE at mbedtls-3.6.7

```
the two interfaces
  include/mbedtls/   74 headers   the legacy interface, mbedtls_* symbols
  include/psa/       23 headers   the PSA Cryptography API, psa_* symbols
  library/psa_crypto*.c   15 files implementing the second one, including psa_crypto.c,
                          psa_crypto_cipher.c, psa_crypto_rsa.c, psa_crypto_ecp.c,
                          psa_crypto_slot_management.c

the project's own statements, all in the tree
  docs/psa-transition.md:7   "Mbed TLS is gradually moving from legacy `mbedtls_xxx` APIs to
                              newer `psa_xxx` APIs for cryptography. Note that this only
                              concerns cryptography APIs, not X.509 or SSL/TLS APIs."
  docs/use-psa-crypto.md:1-6 MBEDTLS_USE_PSA_CRYPTO "makes the X.509 and TLS libraries use
                              PSA for cryptographic operations as much as possible"
  docs/use-psa-crypto.md:15-18 "you need to call `psa_crypto_init()` before calling any
                              function from the SSL/TLS, X.509 or PK modules, except for
                              the various mbedtls_xxx_init() functions"
  README.md:299              "Mbed TLS includes an implementation of the PSA Cryptography
                              API. It covers most, but not all algorithms."
  README.md:301              "The X.509 and TLS code can use PSA cryptography for most
                              operations. To enable this support, activate the compilation
                              option `MBEDTLS_USE_PSA_CRYPTO` ... Note that TLS 1.3 uses PSA
                              cryptography for most operations regardless of this option."
  README.md:305              the driver interfaces "are not fully stable yet and may change
                              without notice"

MARK 7 WAS REPLACED, AND THIS IS WHY
  The v3.6.2 key graded noticing that README.md:6 called the PSA implementation "a preview
  for evaluation purposes only" while docs/psa-transition.md recommended migrating to it.
  At 3.6.7 that sentence IS GONE — `git grep "preview for evaluation"` returns nothing — so
  the old mark was earnable only by asserting something the repository no longer says.
  The tension that IS present, and is harder:
      docs/psa-transition.md      says move to psa_*
      mbedtls_config.h:2230       //#define MBEDTLS_USE_PSA_CRYPTO   <- commented OUT
      => in a DEFAULT build, X.509 and TLS do NOT use PSA internally,
      README.md:301               EXCEPT TLS 1.3, which uses it regardless of the option.
  Related default states worth knowing: mbedtls_config.h:3334 `#define MBEDTLS_PSA_CRYPTO_C`
  is ON (the PSA implementation is built), while :2262 `//#define MBEDTLS_PSA_CRYPTO_CONFIG`
  is OFF (the second configuration namespace is not selected).

the boundary that is easy to get wrong
  the split is CRYPTOGRAPHY only. X.509 and TLS have ONE public interface; there is no
  psa_ equivalent of mbedtls_ssl_* or mbedtls_x509_*.
```

# Q10 — Which functions share state with no call between them?

### Verified facts — SOURCE at mbedtls-3.6.7

```
1. THE BUFFER ALLOCATOR'S FILE-STATIC HEAP
   library/memory_buffer_alloc.c:68   static buffer_alloc_ctx heap;
     written by  mbedtls_memory_buffer_alloc_init (:566), buffer_alloc_calloc (:199),
                 buffer_alloc_free (:362)
     read by     mbedtls_memory_buffer_alloc_verify (:490),
                 mbedtls_memory_buffer_alloc_status (:496),
                 mbedtls_memory_buffer_alloc_max_get (:521),
                 mbedtls_memory_buffer_alloc_cur_get (:533)
     no call reaches any of those readers from any of those writers

2. THE SAME OBJECT, REACHED THROUGH A FUNCTION POINTER — the cleanest instance here
   library/platform.c:44   static void * (*mbedtls_calloc_func)(size_t, size_t)
   library/platform.c:45   static void (*mbedtls_free_func)(void *)
     written by  mbedtls_platform_set_calloc_free (:57)
     read by     mbedtls_calloc (:47) and mbedtls_free (:52), which the whole library calls
     and the WRITER is mbedtls_memory_buffer_alloc_init (memory_buffer_alloc.c:572 with
     threading enabled, :575 without), which installs buffer_alloc_calloc(_mutexed). So
     every mbedtls_calloc in the library ends up in memory_buffer_alloc.c with NO static
     call from the installer to the caller.

3. TWO DIFFERENT FILE-STATICS THAT SHARE A NAME — the trap
   library/psa_crypto.c:124                  static psa_global_data_t global_data;
   library/psa_crypto_slot_management.c:193   static psa_global_data_t global_data;
   These are DIFFERENT objects of DIFFERENT structs that happen to share both names: the
   typedef is defined separately in each file. An answer that reports one `global_data`
   shared between the two files is wrong.

4. THE MUTEXES DOCUMENT THE COUPLINGS THEMSELVES — THIS IS MARK 7
   Re-measured 2026-08-11 at 068ff08 with
     awk 'NR>=133 && NR<=159 {printf "%d: %s\n", NR, $0}' include/mbedtls/threading.h
   include/mbedtls/threading.h:134-143   the key-slot mutex's own comment, quotable verbatim:
       ":137  key_slot_mutex protects the registered_readers and
        :138  state variable for all key slots in &global_data.key_slots."
        :140-143 "This mutex must be held when any read from or write to a state or
                  registered_readers field is performed, i.e. when calling functions:
                  psa_key_slot_state_transition(), psa_register_read(), psa_unregister_read(),
                  psa_key_slot_has_readers() and psa_wipe_key_slot()."
       :144  extern mbedtls_threading_mutex_t mbedtls_threading_key_slot_mutex;
   include/mbedtls/threading.h:146-158   the PSA global_data split, two mutexes for one object:
       :146-150 non-rng members  -> mbedtls_threading_psa_globaldata_mutex  (:151)
       :153-157 rng_state / rng  -> mbedtls_threading_psa_rngdata_mutex     (:158)
   Also :120 readdir_mutex and :130 gmtime_mutex; each of the five is behind its own #if.
   A mutex declared to guard a NAMED object is itself a statement that functions with no call
   between them touch that object — and here the header names the five functions outright, so
   this is the one coupling in mbedtls whose writer/reader set is documented rather than
   inferred. MARK 7 PREVIOUSLY GRADED "says what it did not check", a habit the served
   descriptions teach one arm; it now grades citing this.

5. THE PATTERN RECURS — THIS IS MARK 4
   Items 1, 2 and 3 above are FOUR independent instances in FOUR files:
     library/memory_buffer_alloc.c:68            static buffer_alloc_ctx heap;
     library/platform.c:44-45                    static mbedtls_calloc_func / mbedtls_free_func
     library/psa_crypto.c:124                    static psa_global_data_t global_data;
     library/psa_crypto_slot_management.c:193    static psa_global_data_t global_data;
   Re-measured 2026-08-11 at 068ff08, two commands because the shapes differ:
     git grep -nE '^static (buffer_alloc_ctx heap;|psa_global_data_t global_data;)' -- library/
       -> exactly the 3 object lines above, in 3 files
     git grep -nE '^static (void \*|void) \(\*mbedtls_(calloc|free)_func\)' -- library/platform.c
       -> exactly the 2 pointer lines above (:44 calloc, :45 free)
   A looser one-liner over the same ground also matches library/platform_util.c:91
   `static void *(*const volatile memset_func)(void *, int, size_t) = memset;` — that one is
   `const` and never reassigned, so it is NOT a writer/reader coupling and is not counted here.
   MARK 4 PREVIOUSLY GRADED distinguishing "this codebase has none" from "I did not find any" —
   which `graph_stats.json` and `kconfig.json` state almost verbatim to the index arm. It now
   grades naming instances in at least two DIFFERENT files, i.e. evidencing the recurrence
   rather than being credited for the caution. The surviving half of the old mark is a FACT:
   because these exist, "none" is a wrong answer and not merely an incomplete one.
```

# Q11 — How is this library configured, and how would you turn something on?

### Verified facts — SOURCE at mbedtls-3.6.7

```
WHERE THE DECISION LIVES
  include/mbedtls/mbedtls_config.h   4,446 lines   (v3.6.2 read 4,245)
    142 lines begin `#define MBEDTLS_`     — options ON in the default build   (was 141)
    202 lines begin `//#define MBEDTLS_`   — options present but commented OUT (was 198)
  so a feature is enabled by UNCOMMENTING a line the file already contains, not by
  adding a define. MBEDTLS_THREADING_C at :3787 is exactly this (see Q1), as is
  MBEDTLS_USE_PSA_CRYPTO at :2230 (see Q9).

THE ORDER, ALL OF IT IN include/mbedtls/build_info.h
  :104-105   MBEDTLS_CONFIG_FILES_READ is #error-guarded against double inclusion
  :112-115   MBEDTLS_CONFIG_FILE, if defined, REPLACES mbedtls_config.h wholesale
  :118-121   MBEDTLS_CONFIG_VERSION is range-checked with #error
  :129-130   MBEDTLS_USER_CONFIG_FILE, if defined, is an OVERLAY applied afterwards
  :134-143   MBEDTLS_PSA_CRYPTO_CONFIG selects a SECOND namespace, psa/crypto_config.h,
             itself with MBEDTLS_PSA_CRYPTO_CONFIG_FILE and _USER_CONFIG_FILE overrides
  :179-183   mbedtls/config_adjust_legacy_crypto.h, config_adjust_x509.h,
             config_adjust_ssl.h  — follow dependencies through
             (plus include/psa/crypto_adjust_*.h on the PSA side)
  :192       mbedtls/check_config.h — LAST

WHAT CATCHES AN INCONSISTENT CONFIGURATION
  include/mbedtls/check_config.h contains 202 `#error` directives. An unsatisfiable
  combination fails the COMPILE; there is no runtime check and no warning.

THE SUPPORTED WAYS TO CHANGE IT
  scripts/config.py    reads and sets symbols, and understands that a commented-out #define
                       is a present-but-inactive setting rather than an absent one
  editing by hand      README.md:9 names both routes and points at
                       include/mbedtls/mbedtls_config.h as "also the place where features
                       can be selected"
  configs/             8 complete alternative configurations — config-thread.h,
                       config-no-entropy.h, config-suite-b.h, config-symmetric-only.h,
                       config-ccm-psk-tls1_2.h, config-ccm-psk-dtls1_2.h, config-tfm.h,
                       crypto-config-ccm-aes-sha256.h — plus configs/ext/
```
