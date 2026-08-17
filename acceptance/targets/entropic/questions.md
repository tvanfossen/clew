<!-- SPDX-License-Identifier: MIT -->
---
target: tvanfossen/entropic
commit: 6dcb4c814639fd58ead85aea06809637010f34f1
submodule_llama_cpp: 20a04b22063020cd0f29b7781f5352d7a6abf786
build_version: 32
---

# Q1 — What runs inside entropic's critical sections?

> **Question (frozen).** entropic is a multi-threaded C++ engine. Enumerate the
> mutexes it uses, and for one heavily-used mutex report exactly what executes
> while it is held. How many distinct mutexes does the codebase actually have, and
> how confident are you in that number?

## Marks (11)

- [ ] enumerates the mutexes with their owning class, not as a flat list of bare names
- [ ] **refuses to report a bare declaration count as the number of distinct mutexes**, and
  gives an argued figure with its basis AND the population it counted. Over entropic's own
  code (`src/` + `include/`): 41 declaration sites over 34 names, 40 scalars plus a 23-element
  array, so ~40 declarations against 63 objects per owning instance; the index's lock roster
  restricted to those same trees is 46 rows over 42 distinct `(name, scope)`. Over the WHOLE
  repository as indexed it is 103 rows over 97 distinct, because `extern/llama.cpp` contributes
  54 rows / 52 distinct and `tests/` 3 / 3. Any engine-scoped figure in the 30-45 band passes,
  and so does 97 or 103 when the answer says the figure is whole-repository and separates the
  submodule out. An unattributed 97 does not, because 52 of those mutexes belong to a different
  repository; nor does any number with no basis, in either direction
- [ ] **notices `HookRegistry::mutexes_` is an ARRAY** — one declaration, `ENTROPIC_HOOK_COUNT_`
  == 23 physical `std::shared_mutex` objects, indexed by a runtime hook point — and says which
  way that cuts for a count
- [ ] **for one mutex it names, reports the critical-section EXTENT and what runs inside it** —
  which functions acquire it and what those sections call — and the report checks out against
  the source. Any of entropic's own mutexes is acceptable and the mark is that the extent is
  right; a mutex declared under `extern/llama.cpp` does not satisfy it, because the question
  asks what runs inside entropic's critical sections
- [ ] **reports the acquisition shape and gets it right: every acquisition in entropic's own
  code is scoped RAII**, `lock_guard` 148 / `shared_lock` 13 / `unique_lock` 11 over `src/` +
  `include/`, with no `lock()`/`unlock()` pair in those trees — and reads that as correct for a
  modern-C++ codebase rather than as a gap. `extern/llama.cpp` does lock manually (48
  `lock()`/`unlock()`/`try_lock()` sites over 12 files), so reporting manual locking is a MISS
  only when it is attributed to entropic
- [ ] **finds `entropic_engine::api_mutex` and explains why a guard-site census misses it**: it
  is acquired 21 times through `HandleApiLock`, whose `std::lock_guard` member is bound in a
  constructor initialiser list, so no guard is constructed at any call site. An answer whose
  census is built only on `std::lock_guard` occurrences and does not notice this has missed
  the mutex that serializes entropic's entire public C API
- [ ] **names the `mutex_` collision**: six unrelated classes in entropic's own code declare a
  member literally named `mutex_`, so 30 guard sites and any name-keyed grouping conflate six
  different mutexes. Eight if the submodule is counted — cpp-httplib's `ThreadPool` and ggml's
  `spine_mem_pool_manager` — and either figure passes when the population is stated
- [ ] finds the mutex that is declared and never acquired — `s_session_paths_mu` in
  `src/types/logging.cpp` — or states that it checked for such a case and reports the result
- [ ] **states the confidence honestly and in the right direction**: says which way its own
  method over- and under-counts, rather than reporting one number as settled
- [ ] notices that the long-running public entry points in `src/facade/entropic.cpp`
  deliberately do NOT take `api_mutex` — the comments say a long turn must not block other
  API calls — so "serializes the public API" has a documented exception
- [ ] notes that `HandleApiLock` bundles the mutex with a logging scope and that the member
  order in the class is load-bearing, the comment stating the mutex is acquired first and
  released last

---

# Q2 — Can entropic deadlock?

> **Question (frozen).** Does entropic ever hold two mutexes at once, and if so is
> the acquisition order consistent? Report every case you find and say, for each
> one, how confident you are that it is real.

## Marks (12)

- [ ] **finds the `MCPAuthorizationManager::auth_mutex_` → `MCPKeySet::key_mutex_` nesting** and
  states the mechanism: the authorization manager holds its own mutex and calls into a
  `MCPKeySet` that locks on entry
- [ ] **verifies it at both ends against the source** rather than asserting it — the two class
  headers each document their own locking invariant, and the seven call sites are in one file
- [ ] **finds at least one of the other two real nestings** —
  `SecondaryModelLoader::slots_mutex_` → `InferenceBackend::transition_mutex_` (in
  `release_role` / `shutdown`), or `LlamaCppBackend::mtp_mutex_` → `PromptCache::mutex_` (in
  `do_unload`). An answer that reports the authorization pair as the codebase's ONLY two-lock
  holding is incomplete, and this mark is the one that says so
- [ ] **reports the ORDER as consistent** for whatever it finds — the outer lock is the same one
  every time in all three pairs — so no inversion is demonstrated
- [ ] **argues the no-inversion case structurally rather than by inspection**: `MCPKeySet` never
  names `MCPAuthorizationManager` and `InferenceBackend` never names `SecondaryModelLoader`, so
  the reverse order is not reachable at all for those pairs
- [ ] **does not fabricate a nesting.** Any reported pair whose inner call is a same-named method
  of an unrelated type is a MISS for this mark, however plausible — `.get()` on a
  `std::unique_ptr` is not `SecondaryModelLoader::get`, `.size()` on a container is not
  `MCPKeySet::size`, `.store()` on a `std::atomic` is not `PromptCache::store`
- [ ] **states how it searched and why that method over-reports** on this codebase specifically:
  the inner call is named by an unqualified method name, and several of entropic's own method
  names collide with standard-library member names
- [ ] answers the question that was asked — whether entropic can deadlock — rather than listing
  findings. Consistent ordering in every pair found means no cycle is demonstrated
- [ ] **distinguishes "I found no inversion" from "there is no inversion"**, and says what its
  method could not have seen. A dispatch through a base-class pointer or a `std::function` is
  outside the reach of any static scan of this kind
- [ ] spots that pairs 2 and 3 COMPOSE: `InferenceBackend::unload` calls the virtual
  `do_unload`, so one `release_role` call holds four mutexes in a chain no single function body
  shows
- [ ] notes that `InferenceBackend::unload` fires a consumer-supplied hook callback while holding
  `transition_mutex_`, which is a re-entrancy hazard the source cannot resolve because the
  callback is external
- [ ] quantifies its own precision — states how many candidates its method produced and how many
  survived reading — rather than presenting a filtered list as if it were the raw result

---

# Q3 — Which thread does a function run on?

> **Question (frozen).** How many threads does entropic run, what are they, and for
> a function of your choosing, which thread executes it? Say how much of the
> codebase your answer covers.

## Marks (11)

- [ ] **refuses to answer with a single number**, and says why: two spawn sites are
  per-connection or per-request and two more are per-configured-server, so the live thread
  count is a runtime property, not a source property
- [ ] locates the spawn sites and gives a count of them with its basis, and says which tree the
  count is over — 9 real spawns in `src/` + `include/` is the source figure, and anything close
  passes with the non-spawn tokens excluded and the exclusion explained. The index's thread
  roster is 12 rows over the whole repository, of which only 4 resolve into entropic's own code
  (`ExternalBridge::accept_loop`, `HealthMonitor::monitor_loop`,
  `StdioTransport::stderr_reader_loop`, `SSETransport::sse_reader_loop`), 6 into
  `extern/llama.cpp` and 2 to no file at all — so 12 passes when it is attributed that way and
  an unattributed 12 does not
- [ ] **separates spawns from non-spawns**, naming at least one non-spawn category: a bare
  member declaration (`std::thread accept_thread_;`) and
  `std::thread::hardware_concurrency()` are both `std::thread` tokens and neither starts
  anything
- [ ] **names what at least three of the threads DO**, not just where they are constructed —
  e.g. the accept loop, the health monitor loop, the per-client serve loop, the SSE reader,
  the stderr forwarder
- [ ] **answers the concrete "which thread runs X"** for a function it picks, and traces it to a
  spawn site rather than asserting it
- [ ] **notices the two spawn FORMS** — in entropic's own code, six lambdas against three
  `std::thread(&Class::method, this)` — and says that the lambda bodies have to be read to
  learn the entry point
- [ ] **finds the detached thread.** Exactly one of entropic's own nine detaches
  (`external_bridge.cpp`, the async-ask worker); the other eight are joined. An answer that
  reports the lifecycle uniformly has missed it. Lifecycle claims about `extern/llama.cpp`'s
  threads are neither required nor penalised
- [ ] **quantifies its coverage with a denominator stated** — what fraction of entropic's
  functions its answer actually places on a thread, against what total — and reads silence as
  "not established" rather than as "runs on the main thread"
- [ ] **does not invent a scheduler.** entropic's OWN code has no thread pool, no executor and
  no task queue; every thread of its own is one of the nine `std::thread` constructions. The
  indexed repository does contain one — `class ThreadPool final : public TaskQueue` at
  `extern/llama.cpp/vendor/cpp-httplib/httplib.h:1556` — so naming it AS THE SUBMODULE'S is
  correct and passes; attributing a scheduler to entropic is the MISS
- [ ] notes that the per-client threads are tracked in a `client_threads_` collection guarded by
  its own mutex, so the unbounded set is at least managed rather than merely detached
- [ ] observes that the one detached thread calls back into the public C API (`entropic_run`) on
  the owning handle, so it crosses the facade boundary from the outside

---

# Q7 — Can you edit the codebase and still answer about what you just wrote?

> **Question (frozen).** Add a function named `entropic_acceptance_probe` to
> `src/facade/entropic.cpp`, taking no arguments and returning `int`, with a doxygen
> comment describing it as an acceptance-test probe. Then answer: what is its signature,
> which file does it live in, what is its doxygen brief, does anything call it, and would
> it be visible to a consumer linking against the shipped library?

## Marks (11)

- [ ] **the function is actually added** and is valid C++ — an answer describing an edit that
  was never made is the failure this question exists to catch
- [ ] reports the signature as written, returning `int` and taking no arguments
- [ ] names the file `src/facade/entropic.cpp`
- [ ] reports the doxygen brief it wrote, matching what is in the file
- [ ] **states that nothing calls it**, and does not invent a caller
- [ ] **the reported facts describe the post-edit tree**, not the pre-edit one — the function is
  reported as existing, with no hedging about whether it is there
- [ ] **states what entropic's own guard configuration requires of the new function** —
  `.doxygen-guard.yaml` sets `presence.require_doxygen`, `presence.require_return` and
  `version.require_present`, so a bare `@brief` is not enough
- [ ] **answers the visibility question correctly**: a function added only to
  `src/facade/entropic.cpp` is NOT part of the shipped ABI, because the project compiles with
  hidden visibility and public entry points carry `ENTROPIC_EXPORT` and a declaration in
  `include/entropic/entropic.h`. An answer that says the new function is callable by a
  consumer is wrong
- [ ] the answer is verifiable against the diff — what it says is in the file is in the file
- [ ] notes that `version.require_increment_on_change` is also set, so if the edit had touched
  an existing function's body that function's `@version` would have to be bumped, while a new
  function needs no bump
- [ ] notes that the existing entry points in this file are `extern "C"` and that a C++-mangled
  probe would not match the surrounding convention even if it were exported

---

# Q9 — You have never seen this codebase. Orient.

> **Question (frozen).** You have just been handed this repository and know nothing about
> it. What does it do, where does execution begin, and what are its major subsystems? Give
> the orientation you would want if you had to make a change here tomorrow, and say how much
> of the codebase your answer actually covers.

## Marks (11)

- [ ] describes what the project IS — a local inference engine that runs a GGUF model and
  exposes tool-calling — rather than only listing directories
- [ ] **identifies it as primarily a LIBRARY with a C ABI**, and names
  `include/entropic/entropic.h` or a concrete entry point such as `entropic_create` /
  `entropic_run` as the surface a consumer actually uses
- [ ] **identifies `src/cli/main.cpp` as the program entry point**, and not one of the other
  seven tracked `main` definitions, nor one of the 100 other `main` rows the whole-repository
  index carries
- [ ] **notices there are several `main` functions** and says which are not entropic's own
  program entry. There are eight in tracked C/C++ — `src/cli/main.cpp`, four examples, three
  tests — while the whole-repository index carries 101 `main` rows, 95 of them under
  `extern/llama.cpp`, and misses the two `.c` ones because the Doxyfile's `FILE_PATTERNS`
  omits `*.c`. Either census passes when its population is stated, and an answer naming more
  than one is not over-reporting
- [ ] names at least four real subsystems from
  `inference / mcp / core / facade / config / storage / types / cli / prompts`
- [ ] **weights them rather than listing equals** — `inference` and `mcp` dominate — and states
  what it counted, since the two lead depending on whether private headers are included
- [ ] **identifies `extern/llama.cpp` as a boundary**: the inference work is done by a
  submodule, and that is the single most important structural fact about this repository
- [ ] gives orientation a newcomer could ACT on — where to start reading for a given kind of
  change — not just an inventory
- [ ] **states coverage honestly**: what fraction of the repository the answer rests on and what
  was not looked at, against a denominator it names. `tests/` alone is 238 of 674 tracked
  files; the index's own denominators are 438 first-party indexed files against 1,011 tagged
  external, so either basis passes and an unnamed denominator does not
- [ ] notes that `src/cli/main.cpp` is a subcommand dispatcher whose primary subcommand is
  `mcp-bridge`, so the CLI's main job is to expose the engine to an external MCP client
- [ ] notes that the test tree is larger than `src/` and `include/` combined, and treats it as a
  way in rather than as noise

---

# Q10 — Find a capability when you do not know its name

> **Question (frozen).** Does this codebase implement retry or backoff behaviour anywhere?
> If so, where does it live and how does it work. If not, say so. You are not given a symbol
> name — start from the concept.

## Marks (10)

- [ ] **finds the capability at all** and does not conclude prematurely that it is absent
- [ ] **finds MORE THAN ONE mechanism.** entropic's own code has three unrelated ones; naming
  two passes, naming one does not. *An answer naming three or four is NOT over-reporting — a
  previous key said "two" and would have marked a more complete answer down*
- [ ] names at least one concrete function or file where the behaviour lives
- [ ] **explains the MECHANISM of at least one, not just its location** — what triggers it and
  what bounds it. `ReconnectPolicy::delay_ms` (base × factor^attempt, capped, plus jitter)
  bounded by `exhausted(attempt)`; or `apply_revisions`' bounded loop ending in a rejection
  verdict; or the empty-turn counter with its per-tier ceiling. A location with no trigger and
  no bound MISSES
- [ ] **finds `ReconnectPolicy` specifically.** It is the strongest implementation of the
  capability and NEITHER of its methods is named retry or backoff, so an answer that reached it
  did so by concept — through `HealthMonitor`, through `ReconnectConfig`, through reading
  `src/mcp/`, or through prose — rather than by matching an identifier
- [ ] **searched by concept and says how.** The route is part of the answer here, because the
  identifier route provably does not reach the main mechanism
- [ ] **distinguishes a real policy from incidental naming.** Most of the 19 files in `src/` +
  `include/` mentioning "retry" mention it in prompt text, comments or a buffer resize (123
  files mention it once `extern/llama.cpp` is counted). `retry` in a name is not proof of retry
  behaviour, and here the code with the name is not the code with the backoff
- [ ] **contrasts the mechanisms rather than merging them** — one is timed and exponential, one
  is a bounded loop with no timing at all. An answer that describes "entropic's retry logic" as
  one thing has flattened three
- [ ] **states what it could not determine.** Partial discovery reported as partial is a pass;
  reported as complete is not
- [ ] notices that `max_retries == 0` means infinite rather than none in `ReconnectPolicy`, which
  is the opposite of the natural reading and is the kind of default that decides an incident

---

# Q12 — entropic does not do its own inference. Find the seam.

> **Question (frozen).** entropic wraps a third-party inference library. Where is the
> boundary between entropic's code and that library, how wide is it, and what in entropic
> would break if the library were upgraded? Answer from both trees.

## Marks (13)

- [ ] **identifies `extern/llama.cpp` as a submodule**, not as vendored source, and states that
  it is the only one — `.gitmodules` declares exactly one. The index tags THREE external roots
  (`extern/llama.cpp`, `examples/explorer`, `examples/pychess`) because the two example
  directories hold developer clones on disk, but their contents are entropic's own tracked
  blobs and not gitlinks. "Three submodules" is a MISS; one submodule plus two nested clones of
  tracked example directories passes
- [ ] **reports the pin** — the commit the submodule is fixed at — rather than describing the
  dependency as "llama.cpp" with no version
- [ ] **finds the polymorphic seam**: `LlamaCppBackend` implements the abstract
  `InferenceBackend`, which is declared in a public header and names nothing upstream
- [ ] **quantifies the seam's width** with a real figure — how many of entropic's files include
  an upstream header, or how many distinct upstream symbols are called — and locates it in
  `src/inference/`
- [ ] **checks the public headers and reports what it found there**: zero upstream `#include`s
  under `include/`, which is the fact that makes the boundary a boundary
- [ ] **finds the qualification to that.** Three public headers forward-declare upstream types
  (`llama_model`, `llama_context`, `llama_adapter_lora`), and one public function signature
  takes `const llama_model*`. An answer that reports the public API as fully independent of
  upstream is wrong, and an answer that reports it as coupled without noticing that no header
  is included has missed the distinction
- [ ] **notices entropic depends on upstream's `common` layer, not only on `llama.h`** —
  `<common.h>`, `<chat.h>`, `<sampling.h>`, `<speculative.h>` — and reads that as a wider and
  less stable dependency than the C API. `LLAMA_BUILD_COMMON` being forced ON in
  `extern/CMakeLists.txt` is the corroborating evidence
- [ ] **finds at least one place where entropic COPIES upstream behaviour rather than calling
  it**, and explains why: `speculative_compat.cpp` mirrors a `static` upstream function that
  cannot be called from outside its translation unit, and duplicates two of its constants with
  a keep-in-sync comment. Naming `tool_call_markers.h`'s vendor-coupled marker table instead
  also passes
- [ ] **answers "what would break on an upgrade" concretely**, naming a specific coupling rather
  than saying the API might change — the mirrored constants, the marker table, the `common`
  layer, or the multimodal subdirectory pulled in by path
- [ ] **does not describe the submodule's contents as entropic's code.** `git ls-files extern`
  returns two entries; the submodule's files belong to a different repository and are not
  entropic's to change
- [ ] finds the STALE PIN CLAIM: `src/inference/llama_cpp_backend.cpp`'s file comment names a
  build number that is not the checked-out submodule commit, while `docs/architecture-cpp.md`
  records the actual bump. Full credit requires noticing the two disagree, not merely quoting
  one of them
- [ ] verifies that the mirrored constants are currently IN SYNC by reading both trees, rather
  than only reporting that a sync risk exists
- [ ] notes that `extern/CMakeLists.txt` adds a SECOND subdirectory from inside the submodule
  (`llama.cpp/tools/mtmd`) by path, so the coupling includes upstream's internal directory
  layout and not just its API


