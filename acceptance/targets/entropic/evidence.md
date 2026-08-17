<!-- SPDX-License-Identifier: MIT -->
# entropic — evidence behind the marks

Source facts at 6dcb4c814639fd58ead85aea06809637010f34f1. Nothing here is graded.

# Q0 — INDEX SCOPE: the whole repository, not `src/` + `include/`

Every count below that is labelled with a tree is labelled because gh#333 widened
the index scope, and several marks were originally keyed to a narrower census than
either arm is now looking at. Re-measured 2026-08-10 at build version 32, HEAD
6dcb4c81 clean, submodule at the pinned 20a04b22.

```
WHAT THE INDEX COVERS
  status.scope.source                whole-repo (no index_scope declared)
  graph_stats.files.indexed_files    438     first-party, resolved
  graph_stats.files.external_files  1011     tagged with dg_external_root
  graph_stats.files.unresolved_files 400
  path rows of type=file            1849
    src/ + include/                  201  (190 with symbols)
    tests/                           209  (202)
    examples/                         18  (3)
    extern/llama.cpp                 995  (827)
    other (docs, data, .md, ...)     426  (0)

THE THREE EXTERNAL ROOTS, and only ONE of them is a submodule
  extern/llama.cpp     995 paths   git submodule, declared in .gitmodules
  examples/explorer     11 paths   entropic's OWN tracked blobs (mode 100644);
  examples/pychess       5 paths   a developer clone's .git exists on disk, so the
                                   nested-tree detector tags them external
  `git submodule status` lists exactly one entry. `git ls-files -s examples/explorer`
  returns regular blobs, not gitlinks. So "three external roots" and "one submodule"
  are both true statements about different things.

THE THIRD SCOPE KEY IS STILL UNHANDLED, and it costs two rows
  entropic's Doxyfile FILE_PATTERNS = *.h *.hpp *.cpp *.md
  so tracked `.c` files are NOT indexed: examples/headless/main.c and
  tests/unit/api/header_c99_test.c. Both are `main` definitions the source census
  counts and the index does not.

TRACKED-FILE CENSUS (git ls-files), re-derived and UNCHANGED
  674 total   tests/ 238   src/ 121   include/ 90   examples/ 46   other 179
  `git ls-files extern` still returns exactly two entries.
```

# Q1 — What runs inside entropic's critical sections?

## Key

```
MUTEX DECLARATION SITES                              41   over 34 distinct names
  std::mutex                                         37
  std::shared_mutex (scalar)                          3
  std::array<std::shared_mutex, ENTROPIC_HOOK_COUNT_> 1   HookRegistry::mutexes_,
                                                          include/entropic/core/hook_registry.h:154
  ENTROPIC_HOOK_COUNT_ == 23 (sentinel after
    ENTROPIC_HOOK_ON_COMPLETE = 22,
    include/entropic/types/hooks.h:87-89)
  => 40 scalar declarations + 1 array of 23
  => 63 mutex OBJECTS per instance of the declaring classes, and several of those
     classes are instantiated more than once (one MCPKeySet per registered
     identity), so even 63 is a per-instance figure, not a process-wide count.

DECLARED AND NEVER ACQUIRED                           1
  s_session_paths_mu    src/types/logging.cpp:132 — zero guard sites name it.

THE NAME COLLISION, and it is the reason "how confident" is in the question:
  `mutex_` is the literal member name of SIX unrelated mutexes —
    CompactorRegistry (shared_mutex), ProfileRegistry, ThroughputTracker,
    ToolCallHistory (shared_mutex), SqliteDatabase, PromptCache
  30 of the guard sites name `mutex_`, spread across those six.

RAII GUARD CONSTRUCTION SITES                        172
  std::lock_guard    148      std::shared_lock    13      std::unique_lock    11
  std::scoped_lock     0
  MANUAL lock()/unlock()/try_lock()                  0   — greps for
    `.lock(` `.unlock(` `.try_lock(` `->lock(` `std::lock(` `std::try_lock(`
    over src/ + include/ all return nothing. Every acquisition in this codebase
    is scoped RAII.
  (entropic writes CTAD — `std::lock_guard lock(m);` with no template argument —
   so a census that requires a `<` after the guard type undercounts it.)

  A RAW TOKEN COUNT DISAGREES WITH THE SITE COUNT BY 3, and the three explain
  themselves — this reconciliation is what makes the api_mutex gap attributable
  rather than merely asserted:
    151  raw `std::lock_guard` tokens in src/ + include/
   -  1  engine_handle.h:182 — a MEMBER DECLARATION,
          `std::lock_guard<std::mutex> lock_;`, inside HandleApiLock
   -  2  engine_handle.h:160 and :167 — two DOXYGEN COMMENTS quoting the
          retired idiom `std::lock_guard lock(handle->api_mutex);` as the
          pattern HandleApiLock replaced. Textually indistinguishable from a
          construction, so a grep over-counts api_mutex by exactly these two
          and then finds nothing when it looks for what runs inside them.
    148  real construction sites

THE GUARD TYPE THE CENSUS ABOVE DOES NOT COUNT, and the most important mutex in
the codebase:
  entropic_engine::api_mutex          src/facade/engine_handle.h:76
    Serializes the whole public C API. It has ZERO direct `std::lock_guard`
    sites: a grep for lock_guard near `api_mutex` finds only doxygen comments
    (engine_handle.h:160, :167). Its 21 real acquisitions all go through the
    bespoke RAII wrapper `HandleApiLock` (engine_handle.h:172-184), whose
    `std::lock_guard<std::mutex> lock_;` member is bound in a CONSTRUCTOR
    INITIALISER LIST (`: lock_(h->api_mutex)`, :176) rather than constructed at
    the call site. All 21 sites are in src/facade/entropic.cpp.
  Six comments in entropic.cpp mark the deliberate exception — the long-running
  entry points take the log scope and NOT api_mutex, "a long turn must not block".

WHAT THE INDEX'S LOCK ROSTER REPORTS, and why the mark had to be re-keyed
  lock_roster()                    103 rows / 97 distinct (name, scope)
    src/ + include/                 46 rows / 42 distinct
    extern/llama.cpp                54 rows / 52 distinct
    tests/                           3 rows /  3 distinct
  The buckets sum exactly (42+52+3 = 97, 46+54+3 = 103), so no (name, scope)
  identity is shared across trees.
  The payload's own row_meaning says "Quote distinct_mutexes as the mutex count",
  i.e. it instructs an agent toward 97 — a figure 52 of whose members belong to a
  different repository. Every row does carry its `file`, so the split IS derivable
  from one call; the mark therefore grades attribution, not the digit.
  The engine-only figure (42) already sat inside the pre-existing 30-45 band, which
  is why widening the key was enough and the frozen prompt did not have to change.

TWO FIRST-PARTY MUTEXES THE INDEX ROSTER DOES NOT CARRY, both of them graded
  entropic_engine::api_mutex   locks.source is 'ast_use' only, and HandleApiLock
    binds its guard in a constructor initialiser list, so there is no guard-
    construction site to detect. NEITHER arm gets this mutex from a census; both
    have to read engine_handle.h. The mark is unaffected by scope.
  s_session_paths_mu           declared and never acquired, so a use-derived
    roster cannot contain it by construction. The mark's escape clause ("or states
    that it checked for such a case") is what keeps it reachable.

  HookRegistry's array IS visible, as the literal name `mutexes_[idx]` with
  scope class:HookRegistry — a hint that it is subscripted, not a count of 23.

MANUAL LOCKING, at both scopes
  src/ + include/           0 sites   (verified: `.lock(` `.unlock(` `.try_lock(`
                                       `->lock(` `std::lock(` `std::try_lock(`)
  extern/llama.cpp         48 sites over 12 files — llama-quant.cpp, common/log.cpp,
    tools/server/server-{queue,models,stream}.cpp, tools/imatrix, tools/perplexity,
    vendor/cpp-httplib/httplib.cpp, ggml-threading.cpp, ggml-cann, ggml-vulkan,
    tests/test-quantize-stats.cpp
  So "every acquisition is scoped RAII" is true of entropic and FALSE of the
  repository as indexed.

THE `mutex_` COLLISION AT BOTH SCOPES
  src/ + include/   6 classes   CompactorRegistry, ProfileRegistry, PromptCache,
                                SqliteDatabase, ThroughputTracker, ToolCallHistory
  + submodule       8 classes   adds cpp-httplib's ThreadPool and ggml's
                                spine_mem_pool_manager

RE-VERIFIED FROM SOURCE at this pin (script: .claude/tmp/entropic_scope_audit.py)
  src/ + include/  41 declaration sites / 34 names / 40 scalars + 1 array
    array = include/entropic/core/hook_registry.h:154
            `mutable std::array<std::shared_mutex, ENTROPIC_HOOK_COUNT_> mutexes_;`
    ENTROPIC_HOOK_COUNT_ is the sentinel after ENTROPIC_HOOK_ON_COMPLETE = 22
    (include/entropic/types/hooks.h:87-89), so 23.
  guard tokens  lock_guard 151 (-> 148 real sites)  shared_lock 13  unique_lock 11
  tests/            1 declaration / 14 lock_guard tokens
  examples/         0 declarations
  Every figure the Q1 key quoted is confirmed unchanged; only the POPULATION it
  described was left unstated.

A WORKED EXTENT, for grading whichever mutex an answer picks
  MCPAuthorizationManager::auth_mutex_   include/entropic/mcp/mcp_authorization.h:148
    10 guard sites in src/mcp/mcp_authorization.cpp, one at the top of each of the
    class's ten public methods — register_identity, is_enforced, grant, revoke,
    check_access, grant_from, list_keys, serialize_all, deserialize_all,
    unregister_identity. The header states the invariant itself at :20: "All
    public methods acquire auth_mutex_."
    What runs inside: a `key_sets_` map lookup in every one; and in seven of the
    ten, a call into MCPKeySet that takes a SECOND mutex — see Q2.
```

# Q2 — Can entropic deadlock?

## Key

```
THREE REAL CROSS-FUNCTION NESTINGS, all with a consistent order.

1. MCPAuthorizationManager::auth_mutex_  ->  MCPKeySet::key_mutex_        7 methods
   src/mcp/mcp_authorization.cpp — each method takes auth_mutex_ on its first
   statement, then calls a method on the MCPKeySet stored in `key_sets_`, and
   every one of those MCPKeySet methods takes key_mutex_ on ITS first statement:
     grant           :52  -> MCPKeySet::grant        (mcp_key_set.cpp:24/:26)
     revoke          :73  -> MCPKeySet::revoke       (:39/:40)
     check_access    :94  -> MCPKeySet::has_access   (:58/:60)
     grant_from     :123  -> has_access AND grant
     list_keys      :154  -> MCPKeySet::list         (:72/:73)
     serialize_all  :170  -> MCPKeySet::serialize    (:109/:110)
     deserialize_all:187  -> MCPKeySet::clear AND MCPKeySet::deserialize
   Documented at both ends: mcp_authorization.h:20 "All public methods acquire
   auth_mutex_"; mcp_key_set.h:18-19 "grant/revoke acquire key_mutex_.
   has_access() acquires key_mutex_ for consistency. Serialization acquires
   key_mutex_."
   NO INVERSION IS POSSIBLE: MCPKeySet names MCPAuthorizationManager zero times
   in its header and zero times in its implementation.

2. SecondaryModelLoader::slots_mutex_  ->  InferenceBackend::transition_mutex_  2 methods
   src/inference/secondary_model_loader.cpp
     release_role  :95   holds slots_mutex_, calls it->second->unload()
     shutdown     :159   holds slots_mutex_, calls backend->unload()
   InferenceBackend::unload (src/inference/backend.cpp:139) takes
   transition_mutex_ at :140. backend.h:13 states the invariant:
   "load/activate/deactivate/unload acquire transition_mutex_".
   NO INVERSION: InferenceBackend names SecondaryModelLoader zero times.

3. LlamaCppBackend::mtp_mutex_  ->  PromptCache::mutex_                    1 method
   LlamaCppBackend::do_unload (src/inference/llama_cpp_backend.cpp:744) takes
   mtp_mutex_ at :745, then calls prompt_cache_->clear() at :747;
   PromptCache::clear (src/inference/prompt_cache.cpp:183) takes mutex_ at :184.
   `prompt_cache_` is a std::unique_ptr<PromptCache> member
   (llama_cpp_backend.h:674).

AND 2 AND 3 COMPOSE INTO A THREE-DEEP CHAIN:
  InferenceBackend::unload holds transition_mutex_ and calls the virtual
  do_unload() at backend.cpp:152, so a release_role() call holds, in order:
    slots_mutex_ -> transition_mutex_ -> mtp_mutex_ -> PromptCache::mutex_
  Four mutexes deep, in one consistent order, and no single function's body
  shows more than one hop of it.

ALSO INSIDE A CRITICAL SECTION, and worth spotting:
  InferenceBackend::unload fires the ON_MODEL_UNLOAD hook (backend.cpp:143-148)
  WHILE holding transition_mutex_ — a consumer-supplied callback invoked under a
  lock. Not a nesting the source can resolve, because the callback is external.

THE FALSE POSITIVES A NAME SEARCH PRODUCES HERE, all verified as NOT nestings:
  ModelOrchestrator::get_model holds swap_mutex_ and calls `it->second.get()` —
    that is std::unique_ptr::get, not SecondaryModelLoader::get / ProfileRegistry::get
    / GrammarRegistry::get.
  ModelOrchestrator::residency_snapshot_json holds swap_mutex_ and calls
    backend->is_loaded() — that is InferenceBackend::is_loaded, which does NOT
    lock (backend.h:15: state queries "do NOT acquire transition_mutex_"), not
    SecondaryModelLoader::is_loaded, which does.
  A dozen more of the same shape: `.size()`, `.clear()`, `.store()` on standard
  containers and atomics matching MCPKeySet::size, PromptCache::clear,
  PromptCache::store.

WHAT THE INDEX'S NESTING LAYER REPORTS, and it is mostly the mark's own trap
  lock_nestings()   26 pairs at the widened scope. NO MARK NEEDED RE-KEYING, because
  the marks grade the ordering argument and the false-positive discipline rather than
  a pair count — but a grader should recognise these rows:
    REAL, and pair 1 above       auth_mutex_ -> key_mutex_ via has_access
                                 (check_access :105, grant_from :135)
    REAL, submodule              WebSocket::ping_mutex_ -> WebSocket::write_mutex_
                                 (httplib.cpp:16429, via_resolution 'resolved')
    REAL, submodule              vulkan device->mutex -> queue_mutex (4 rows);
                                 cann tracker->mtx -> tracker_mutex / workspace mtx
    FABRICATED, 14 rows          `X -> PromptCache::mutex_ via store` — that `store`
                                 is std::atomic::store or a map insert, NOT
                                 PromptCache::store. Exactly the shape mark 6 names.
                                 Every one carries via_resolution
                                 'receiver_unverified', which is the discriminator
                                 the index arm has available.
    NOT FOUND                    pairs 2 and 3 (slots_mutex_ -> transition_mutex_,
                                 mtp_mutex_ -> PromptCache::mutex_ via clear), so
                                 mark 3 stays a real discriminator for both arms.
  Order is consistent in every submodule pair too, so mark 4's substance ("no
  inversion is demonstrated") holds at either scope.

COMPLETENESS, stated honestly: the search above is an ownership-filtered scan of
  every lock-holding member function in src/, and it is not a proof. A nesting
  reached through a base-class pointer whose dynamic type is not a declared
  member, or through a std::function, would not appear. No inversion was found;
  "no inversion exists" is not established.
```

# Q3 — Which thread does a function run on?

## Key

```
'std::thread' / 'std::jthread' TOKENS, excluding #include lines        19
  REAL SPAWNS                                                           9
    src/core/response_generator.cpp:413   lambda   cancel observer; joined :429
    src/facade/external_bridge.cpp:796    lambda   accept_thread_ -> accept_loop();
                                                   joined :833
    src/facade/external_bridge.cpp:945    lambda   PER CLIENT: ct->thread ->
                                                   serve_client(fd); joined :850/:884
    src/facade/external_bridge.cpp:1158   lambda   PER ASYNC ASK: runs entropic_run;
                                                   DETACHED at :1222
    src/inference/inference_c_api.cpp:385 lambda   poller_; joined :403
    src/inference/interface_factory.cpp:246 lambda poller; joined :262
    src/mcp/health_monitor.cpp:92         &member  HealthMonitor::monitor_loop; joined :108
    src/mcp/transport_sse.cpp:107         &member  SSETransport::sse_reader_loop; joined :139
    src/mcp/transport_stdio.cpp:164       &member  StdioTransport::stderr_reader_loop;
                                                   joined :219
  NOT SPAWNS                                                           10
    5 member declarations in headers (external_bridge.h:387 accept_thread_, :400
      ClientThread::thread, health_monitor.h:136, transport_sse.h:93,
      transport_stdio.h:157)
    3 local declarations later assigned (response_generator.cpp:410,
      inference_c_api.cpp:419, interface_factory.cpp:244)
    2 std::thread::hardware_concurrency() calls (llama_cpp_backend.cpp:332,
      profile_registry.cpp:35) — a static query, not a spawn

SPAWN FORMS DIFFER, and this is what a purely textual census flattens:
  6 lambdas, 3 member-function-pointer form `std::thread(&Class::method, this)`.
  A lambda body has to be read to learn what the thread runs; the pointer form
  names its entry in the construction itself.

LIFECYCLE                                       exactly ONE detached thread
  8 of 9 are joined; external_bridge.cpp:1158 is the only `.detach()` in
  src/ + include/ (at :1222).

THERE IS NO STATIC THREAD COUNT, and this is the load-bearing fact:
  external_bridge.cpp:945   one thread PER CONNECTED CLIENT
  external_bridge.cpp:1158  one detached thread PER ASYNC ASK
  transport_sse.cpp:107 / transport_stdio.cpp:164  one thread PER CONFIGURED
    EXTERNAL MCP SERVER — the count comes from configuration, not from source
  response_generator.cpp:413 / inference_c_api.cpp:385 / interface_factory.cpp:246
    are per-operation, spawned and joined inside the call
  So the only spawn sites that yield exactly one long-lived thread per engine are
  the accept thread and the health monitor.

CONCURRENCY PRIMITIVE INVENTORY (for "what are they")
  no thread pool, no executor, no task queue library IN ENTROPIC'S OWN CODE — every
  thread of entropic's own is a std::thread constructed at one of the nine sites
  above.
  BUT THE INDEXED REPOSITORY HAS ONE, and this is what made the old key unfair:
    extern/llama.cpp/vendor/cpp-httplib/httplib.h:1556
      `class ThreadPool final : public TaskQueue { ... };`
    with its `mutex_` member visible in the lock roster and its `worker` thread in
    the thread roster. An index-arm agent that reported "there is a thread pool"
    was correct about the repository it was pointed at and would have been marked
    down for inventing a scheduler. The mark now grades ATTRIBUTION.

WHAT THE INDEX'S THREAD ROSTER REPORTS
  thread_roster()   12 rows, all kind 'pthread', all source 'ast_spawn',
                    all confidence 'medium'
    ENTROPIC (4)   accept_loop                     src/facade/external_bridge.cpp
                   HealthMonitor::monitor_loop     src/mcp/health_monitor.cpp
                   StdioTransport::stderr_reader_loop  src/mcp/transport_stdio.cpp
                   SSETransport::sse_reader_loop   src/mcp/transport_sse.cpp
    SUBMODULE (6)  worker / run_event_loop / listen_after_bind  (cpp-httplib)
                   compute                         (ggml-cpu/llamafile/sgemm.cpp)
                   log_mel_spectrogram_worker_thread  (tools/mtmd/mtmd-audio.cpp)
                   gc_loop                         (tools/server/server-stream.cpp)
    NO ENTRY FILE (2)  prepare, entryProc — entry_memberdef_rowid does not resolve
  So 12 is NOT "9 plus rounding": it is 4 of entropic's 9 plus 8 rows that are not
  entropic's. Five of entropic's nine spawns yield no thread row at all — the
  multi-call-lambda entries stay fail-closed by design.
```

# Q7 — Can you edit the codebase and still answer about what you just wrote?

## Key

```
src/facade/entropic.cpp                4,123 lines at v2.9.20, an existing file
entropic_acceptance_probe              ABSENT — zero matches anywhere in the tree,
                                       so this question is not pre-satisfied
callers of a brand-new symbol          0, necessarily

WHAT ENTROPIC'S OWN DECLARED CONVENTIONS REQUIRE OF THE EDIT
  .doxygen-guard.yaml (repo root):
    validate.presence.require_doxygen        true
    validate.presence.require_return         true
    validate.version.require_present         true
    validate.version.require_increment_on_change  true
  So a new function needs @brief, @return and a @version tag; and because the
  increment rule is on, touching an EXISTING function's body in the same edit
  would require bumping that function's @version. A brand-new function starts at
  its initial version and needs no bump.

VISIBILITY — the fact most answers will get wrong
  CMakeLists.txt:34   set(CMAKE_CXX_VISIBILITY_PRESET hidden)
  include/entropic/entropic_export.h:28
      #define ENTROPIC_EXPORT __attribute__((visibility("default")))
  Every shipped public entry point is declared ENTROPIC_EXPORT in
  include/entropic/entropic.h (94 occurrences) and defined `extern "C"` in
  src/facade/entropic.cpp. A plain function added to that .cpp and to no header
  is therefore NOT exported from the shared library: it compiles, it is real, and
  a consumer cannot link to it.
```

# Q9 — You have never seen this codebase. Orient.

## Key

```
WHAT IT IS
  README.md: "a C inference engine that turns a local GGUF model into a
  multi-tier, tool-calling AI system", local-first, no cloud.
  It is primarily a LIBRARY with a C ABI: include/entropic/entropic.h declares
  94 ENTROPIC_EXPORT entry points (entropic_create, entropic_configure,
  entropic_run, entropic_run_streaming, ...). The CLI is a thin consumer of it.

THE `main` TRAP, re-derived from TRACKED source
  8 `main` definitions in tracked .c/.cc/.cpp, exactly ONE of which is
  entropic's own program entry:
    src/cli/main.cpp                              <- THE entry point; builds the
                                                     `entropic` executable
                                                     (src/cli/CMakeLists.txt:8)
    examples/explorer/main.cpp                    example  -> `explorer`
    examples/headless/main.c                      example  -> `headless`
    examples/openai-server/src/main.cpp           example  -> `entropic-openai-server`
    examples/pychess/main.cpp                     example  -> `pychess`
    tests/distribution-smoke-consumer/smoke.cpp   test
    tests/helpers/mock_mcp_server.cpp             test helper
    tests/unit/api/header_c99_test.c              test
  plus 5 Python `def main` (examples/pychess/main.py, main_wrapper.py,
    python/src/entropic/cli.py, install_engine.py, scripts/gen_bindings.py)
  and 94 more files defining `main` inside extern/llama.cpp, which is a
  submodule and a different repository.

  What src/cli/main.cpp actually is (its own file comment): a subcommand
  dispatcher whose primary subcommand is `entropic mcp-bridge`, speaking
  JSON-RPC 2.0 over stdio. "Where execution begins" for most users is
  entropic_create() in the library, not this file.

SUBSYSTEMS — tracked files per src/ subdirectory, and the ranking DEPENDS on
what you count, which is itself worth noticing:
                  tracked   .c/.cpp   private .h
    inference        38        22         15
    mcp              26        25          0
    core             14        13          0
    facade           13         8          4
    config            8         6          1
    storage           7         6          0
    types             7         6          0
    cli               5         4          0
    prompts           3         2          0
    TOTAL           121        92         20   (+ 9 CMakeLists.txt)
  By total files inference leads; by implementation files mcp leads. inference
  carries 15 of the repository's 20 private headers.
  include/entropic/: 90 tracked, 89 headers — mcp 26, types 15, core 14,
    inference 13, storage 7, interfaces 6, config 4, prompts 2, root 3.

WHAT THE INDEX'S `main` CENSUS REPORTS, at the widened scope
  101 rows named `main` with kind 'function'
    engine       1   src/cli/main.cpp                     <- still the only one
    examples     3   explorer/main.cpp, openai-server/src/main.cpp, pychess/main.cpp
    tests        2   distribution-smoke-consumer/smoke.cpp, helpers/mock_mcp_server.cpp
    submodule   95   extern/llama.cpp/{examples,tools,tests,pocs,app,ggml}/...
  MISSING vs the tracked census, and it is the FILE_PATTERNS hole, not a real absence:
    examples/headless/main.c, tests/unit/api/header_c99_test.c
  So the tracked figure is 8 and the indexed figure is 101, and both are correct
  about their own population. "The other seven" was only ever true of the first.

BOUNDARIES
  extern/llama.cpp — the one submodule (see Q12)
  include/entropic/entropic.h — the C ABI, the stable surface
  tests/ is 238 tracked files, larger than src/ and include/ combined
  the index's own coverage denominators: 438 first-party indexed files against
  1,011 tagged external — a different, equally citable basis for the same claim
```

# Q10 — Find a capability when you do not know its name

## Key

```
WHAT A NAME SEARCH FINDS, and why it is the weaker half
  function names containing retry : 5 distinct
    ConstitutionalValidator::set_auto_retry / auto_retry_enabled / resume_retry
    entropic_validation_set_auto_retry / entropic_validation_resume_retry (C facade)
  function names containing backoff : ZERO.
  files in src/ + include/ mentioning retry|retries|backoff anywhere : 19,
    most of them incidentally — prompt text telling a model "Do NOT retry it"
    (tool_executor.cpp), a comment about `--continue-at` (download.cpp), a
    buffer-resize retry in llama_cpp_tokenizer.cpp.
  the same grep once extern/llama.cpp is in scope : 123 files. The three mechanisms
    below are entropic's own; the widened scope only makes the incidental-naming
    problem the mark grades LARGER, it does not move any of the three.

THREE UNRELATED REAL MECHANISMS, and they work differently from each other.

1. TIMED EXPONENTIAL BACKOFF — src/mcp/reconnect_policy.cpp, class ReconnectPolicy.
   NEITHER of its two methods is named retry or backoff:
     ReconnectPolicy::delay_ms(attempt)
       base_delay_ms_ * pow(backoff_factor_, attempt), capped at max_delay_ms_,
       plus uniform jitter in [0, 10% of the capped delay]
     ReconnectPolicy::exhausted(attempt)
       attempt >= max_retries_, and max_retries_ == 0 means INFINITE
   Trigger and bound from the caller: HealthMonitor::attempt_reconnect
   (src/mcp/health_monitor.cpp:204) checks policy_.exhausted() FIRST, marks the
   server "error" and stops if so; otherwise tries client->connect() and on
   failure schedules the next attempt at delay_ms(attempt).
   Constructed at src/mcp/server_manager.cpp:510 from ReconnectConfig
   (include/entropic/types/config.h:626): base_delay_ms 1000, max_delay_ms 60000,
   max_retries 5, backoff_factor 2.0.
   => genuine exponential backoff with jitter and a configurable cap.

2. ATTEMPT-BOUNDED REVISION LOOP, no timing — ConstitutionalValidator.
   apply_revisions (src/core/constitutional_validator.cpp:575) is
   `for (int i = 0; i < config_.max_revisions; ++i)` with a length safety valve
   that rejects a revision shrinking content by more than half. No delay, no
   backoff. set_auto_retry(false) makes validation stop at the first failing
   critique and cache state; resume_retry() re-enters from that cache. So the
   name-matched mechanism is a consumer-driven CONTROL over a bounded loop.

3. EMPTY-TURN ALLOWANCE IN THE AGENT LOOP — this release's own feature.
   AgentEngine::record_explicit_completion_failure (src/core/engine.cpp:771)
   keeps a counter in ctx.metadata["zero_tool_call_retries"], ceiling default 3
   with a per-tier override `max_consecutive_empty_turns`; under the ceiling it
   appends a "[SYSTEM] ... Retry." correction message and re-enters EXECUTING,
   at the ceiling it sets failure_reason and transitions to ERROR.
   (gh#123, and the v2.9.20 release commit is literally "empty-turn allowance:
   plumbing, semantic fix, default 3".)

A FOURTH, TRIVIAL ONE, and it is fine either to name or to omit:
  llama_cpp_tokenizer.cpp — a single immediate retry with an exact-size buffer
  after a sized call returns the required size as a negative. Mechanically a
  retry; architecturally not a policy.

So the honest answer is "yes, in at least three unrelated places, and they work
differently": one is timed exponential backoff, one is a bounded loop with no
timing, one is a bounded re-prompt in the agent loop. An answer naming only the
name-matched one has found the weakest of the three.
```

# Q12 — entropic does not do its own inference. Find the seam.

## Key

```
THE SUBMODULE                                                     exactly one
  .gitmodules: [submodule "extern/llama.cpp"]
    path extern/llama.cpp, url https://github.com/ggml-org/llama.cpp.git
  pinned at 20a04b22063020cd0f29b7781f5352d7a6abf786
  `git ls-files extern` returns TWO entries: extern/CMakeLists.txt and the
  extern/llama.cpp gitlink. The submodule's contents are not files of this
  repository.

  THE INDEX NAMES THREE EXTERNAL ROOTS, AND ONLY THIS ONE IS A SUBMODULE.
  status/graph_stats report external_roots = examples/explorer, examples/pychess,
  extern/llama.cpp (1,011 tagged paths, 995 of them the submodule's). The two
  example directories are tagged because a developer clone's `.git` sits inside
  them on disk; `git ls-files -s examples/explorer examples/pychess` returns mode
  100644 blobs, so those files ARE entropic's own and ARE tracked by entropic.
  An index-arm agent reading external_roots is therefore steered toward "three
  external trees", which is true, and away from "one submodule", which is the
  answer to the question. The mark now says which of those two claims it grades.

  The 995 submodule paths are INDEXED, not excluded (gh#335), so an index-arm
  agent can see llama.cpp's symbols and must still not call them entropic's —
  dg_external_root is the tag that lets it tell them apart.

HOW IT IS BUILT — extern/CMakeLists.txt
  add_subdirectory(llama.cpp EXCLUDE_FROM_ALL) with
    LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS  OFF
    LLAMA_BUILD_COMMON                       ON   <- deliberately
    GGML_CUDA bridged from ENTROPIC_HAS_CUDA
  and a SECOND add_subdirectory for llama.cpp/tools/mtmd (multimodal), built
  out of the same submodule into a separate binary dir.
  EXCLUDE_FROM_ALL is there to suppress upstream's install rules: "our facade
  absorbs libllama.a as a static dependency; consumers never link to llama
  directly."

HOW WIDE THE SEAM IS
  files in src/ that include an upstream header DIRECTLY                  9
    all under src/inference/: adapter_manager.cpp, grammar_registry.cpp,
    llama_cpp_backend.{h,cpp}, llama_cpp_sampler.cpp, llama_cpp_tokenizer.cpp,
    orchestrator.cpp, speculative_compat.cpp, tool_call_markers.h
  files including the PRIVATE src/inference/llama_cpp_backend.h              6
    llama_cpp_backend.cpp, orchestrator.cpp, inference_c_api.cpp,
    interface_factory.cpp, secondary_model_loader.cpp, and
    src/facade/entropic.cpp — the only one outside src/inference/
  distinct upstream symbols called from src/
    llama_*   61      mtmd_*   14      ggml_*   3      common_*  23
    (of the 23 `common_*` names, at least two are entropic's OWN helpers named
     in upstream's style: LlamaCppBackend::common_chat_parse_reliable, and the
     `common_prefix_len` template in src/inference/warm_keep_util.h. Upstream
     also has a `common_prefix_len`, but it is `static` inside
     common/chat-auto-parser-helpers.cpp with a different signature, so this is
     a naming convergence and NOT a link-time collision — do not grade it as one.)
  the polymorphic seam: `class LlamaCppBackend : public InferenceBackend`
    (src/inference/llama_cpp_backend.h:65). InferenceBackend is declared in the
    PUBLIC header include/entropic/inference/backend.h and names nothing upstream.

THE BOUNDARY IS ALMOST, BUT NOT QUITE, CLEAN
  ZERO upstream headers are #included anywhere under include/ — verified
  recursively over all 89 public headers.
  BUT three public headers FORWARD-DECLARE upstream types, six declarations:
    include/entropic/inference/adapter_manager.h:37-39
        struct llama_model; struct llama_context; struct llama_adapter_lora;
    include/entropic/inference/orchestrator.h:44-45
        struct llama_context; struct llama_model;
    include/entropic/inference/speculative_compat.h:47
        struct llama_model;   (and its signature takes const llama_model*)
  So the public API compiles without upstream's headers but is not independent
  of upstream's type NAMES.

WHAT BREAKS ON AN UPGRADE — four named couplings, each checkable
  1. entropic uses upstream's `common` library, not only the stable llama.h C
     API: <common.h>, <chat.h>, <sampling.h>, <speculative.h> are included by
     llama_cpp_backend.cpp and tool_call_markers.h. LLAMA_BUILD_COMMON is forced
     ON for this. `common` is upstream's example-support layer, not its ABI.
  2. src/inference/speculative_compat.cpp MIRRORS a file-private upstream
     function. Its own comment: "Mirrors the file-private
     common_speculative_are_compatible function from
     extern/llama.cpp/common/speculative.cpp". Upstream's is
     `static bool common_speculative_are_compatible(...)` at
     extern/llama.cpp/common/speculative.cpp:64 — static, therefore unreachable.
     entropic duplicates two of its constants:
       kSpecVocabMaxSizeDifference = 128   vs upstream SPEC_VOCAB_MAX_SIZE_DIFFERENCE
       kSpecVocabCheckStartTokenId = 5     vs upstream SPEC_VOCAB_CHECK_START_TOKEN_ID
       (extern/llama.cpp/common/speculative.cpp:28-29)
     VERIFIED IN SYNC at this pin: 128 == 128 and 5 == 5. The comment says
     "Keep in sync ... if upstream tightens", so this is a live drift risk that
     is currently not drifting.
  3. src/inference/tool_call_markers.h maps a resolved chat format to a
     tool-call close marker, and its comment says the table tracks upstream's
     PEG parser defaults and is "vendor-coupled and MUST be re-checked on a
     llama.cpp pin bump". (Its cited line for upstream's `section_end` default
     no longer resolves exactly — the default `</tool_call>` is at
     extern/llama.cpp/common/chat-peg-parser.cpp:436 at this pin. A line-level
     citation drift, not a behavioural one, and this rubric does not grade lines.)
  4. src/inference/mtp_envelope.h documents a guard that was REMOVED because the
     pin moved: an upstream flash-attention fix let entropic drop a restriction
     it had been carrying.

A STALE PIN CLAIM IN THE SOURCE, checkable in one line
  src/inference/llama_cpp_backend.cpp:6 says "Pinned against llama.cpp submodule
  b8420." The submodule is actually at 20a04b22, and docs/architecture-cpp.md:943
  records that bump (`ac4cddeb` -> `b9886`, i.e. 20a04b22) as part of gh#108.
  The file comment was not updated with the pin. Two statements inside one
  repository disagree, and the git state arbitrates.
```
