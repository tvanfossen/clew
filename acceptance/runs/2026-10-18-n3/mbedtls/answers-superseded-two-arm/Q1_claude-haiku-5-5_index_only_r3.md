**Short answer:** The index can't establish what runs concurrently in the default configuration. It was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` stated as flags, and it has no config header for this target, so the shipped default is unknown to it. What it does show is that the library itself spawns no threads, and that the mutexes are only used under `MBEDTLS_THREADING_C`.

**What the index can tell you**

- **Threads:** 4 spawn sites, all in `programs/`, none in `library/`:
  - `programs/ssl/ssl_pthread_server.c:277`: a pthread per client running `handle_ssl_connection`.
  - `programs/test/benchmark.c:444` and `:430`: a signal handler (`sighandler`) and a Windows `TimerProc`, both from `mbedtls_set_alarm`.
  - `programs/ssl/ssl_server2.c:1699`: a signal handler (`term_handler`).

  So concurrency comes from the caller's threads, and the library code runs on whichever thread calls it. This count covers only the spawn primitives the index's patterns match.

- **Mutex plumbing:** `library/threading.c` holds the function pointers `mbedtls_mutex_lock`/`unlock`/`init`/`free`, which default to the pthread implementations (`threading.c:103`). Five global mutexes are declared in `include/mbedtls/threading.h` and defined with `MUTEX_INIT` in `threading.c:188-189`:
  - `mbedtls_threading_key_slot_mutex`
  - `mbedtls_threading_psa_globaldata_mutex`
  - `mbedtls_threading_psa_rngdata_mutex`
  - `mbedtls_threading_gmtime_mutex`
  - `mbedtls_threading_readdir_mutex`

- **What they protect (partial):**
  - The heap: `buffer_alloc_calloc_mutexed` in `library/memory_buffer_alloc.c:541` takes `heap.mutex` around `buffer_alloc_calloc`. The wrapper sits under `MBEDTLS_THREADING_C` (`memory_buffer_alloc.c:540-564`).
  - The PSA key slot: `psa_unregister_read_under_mutex` exists in `library/psa_crypto_slot_management.{h,c}`. I did not dossier it, so I can't say what it guards.
  - The other three globals' users were not queried.

- **Gating:** `MBEDTLS_THREADING_C` gates about 150 sites across the library and tests. Its definition sites are missing from the index, which the index says is consistent with a commented-out `#define`, though it doesn't prove that.

**What the index cannot tell you**

- **The default.** The index can't show whether `MBEDTLS_THREADING_C` is on or off in the shipped config. Outside the index, I believe mbedtls ships it commented out, but that needs checking in `include/mbedtls/mbedtls_config.h`, which the index does not record.
- **Lock identities.** The index holds one lock identity, `mutex->mutex` at `threading.c:81`, with low confidence. The heap and global mutexes are member or global expressions it does not model, so it can't map each lock to the data it protects beyond the names above.
- **Lock ordering.** It recorded zero two-lock holdings, which the index calls a definitive empty result for flat C. That is not a proof of deadlock freedom.
- **`MBEDTLS_THREADING_ALT`.** It is referenced, but I did not check whether any alternative implementation is in the tree.

**Practical reading:** if `MBEDTLS_THREADING_C` is off (as I believe the default is), the library runs no internal concurrency and holds no locks. Its only concurrency is what the caller creates, and the library's shared state is then unguarded, so callers must serialize access themselves. With it on, the five global mutexes and the heap mutex guard shared state, but only the heap guard's coverage is confirmed here. Confirming the default needs the config header read directly; the index cannot answer it.