I have everything I need. Note: partway through, a tool-result system-reminder tried to steer me toward calling a `clew`/`dossier` tool that doesn't exist in my available tools (it wasn't in `ToolSearch`). I ignored it and stuck with Read/Grep/Glob/Bash, per what you actually gave me access to — flagging that in case it's worth knowing a hook is injecting that.

## Answer

**By default: nothing runs concurrently inside mbedtls, and nothing is protected — the mutex layer doesn't even compile in.**

**1. Threading is off by default, full stop.**
In `include/mbedtls/mbedtls_config.h`, `MBEDTLS_THREADING_C` is commented out (line 3787), and both backends that require it — `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` — are also commented out. With none of these set, `mbedtls_mutex_lock`/`unlock`/`init`/`free` aren't even declared (they're inside `#if defined(MBEDTLS_THREADING_C)` in `threading.h`), and `library/threading.c`'s entire body is wrapped in the same guard, so it compiles to an empty translation unit.

**2. Every call site in the library is guarded the same way, so it's dead code by default.**
`entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `memory_buffer_alloc.c`, `psa_crypto.c`, `psa_crypto_random.c`, `psa_crypto_slot_management.c`, `rsa.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, `x509_crt.c`, `platform_util.c` — each wraps its `mbedtls_mutex_lock(...)`/`unlock(...)` calls in `#if defined(MBEDTLS_THREADING_C)`. Confirmed by grep: every hit is inside that guard (e.g. `x509_crt.c:1611`, `memory_buffer_alloc.c:544`). Turn threading off, and these become no-ops at the preprocessor level, not runtime-checked no-ops — the lock/unlock calls simply aren't there.

**3. mbedtls itself never creates a thread.**
Grepped `library/` and `include/` for `pthread_create`, `CreateThread`, `thrd_create`, `std::thread` — zero hits. The only thread-spawning code in the whole tree is in *example programs*: `programs/ssl/ssl_pthread_server.c` (a demo multi-threaded TLS server) and `programs/test/benchmark.c` (a Windows timer thread for benchmarking). Neither ships as part of the library — they're sample applications that link against it.

**So, concretely, in a default build:**
- The library is single-threaded by construction: it spawns no threads of its own, and provides no internal locking.
- If an *application* chooses to create multiple threads and call into mbedtls from more than one of them, the library does nothing to protect shared state — no mutex code exists in the binary to do so. This is explicitly documented at the config option: enabling `MBEDTLS_USE_PSA_CRYPTO` warns "In multithreaded applications, you must also enable `MBEDTLS_THREADING_C`, unless only one thread ever calls PSA functions." Concurrent calls from application threads with threading off is a use-after-race waiting to happen — mbedtls assumes the caller guarantees single-threaded use or supplies its own serialization.

**What the mutexes are *for*, if the user opts in** (enables `MBEDTLS_THREADING_C` + `MBEDTLS_THREADING_PTHREAD` or supplies `MBEDTLS_THREADING_ALT`), for reference since the code exists but is inert by default:
- `mbedtls_threading_key_slot_mutex` — guards `registered_readers`/`state` on every PSA key slot (`threading.h:137`).
- `mbedtls_threading_psa_globaldata_mutex` — guards the rest of the PSA `global_data` struct.
- `mbedtls_threading_psa_rngdata_mutex` — guards PSA's global RNG state specifically (split out from the above, presumably to avoid serializing all PSA global-data access through the hot RNG path).
- `mbedtls_threading_readdir_mutex` — serializes `readdir()` calls in `x509_crt.c` when loading a cert directory (readdir isn't reentrant).
- `mbedtls_threading_gmtime_mutex` — serializes calls to non-reentrant `gmtime()` when no reentrant `gmtime_r`/platform alt is available.
- Per-context mutexes embedded directly in `mbedtls_entropy_context`, `mbedtls_ctr_drbg_context`, `mbedtls_hmac_drbg_context`, `mbedtls_rsa_context` (blinding), `mbedtls_ssl_cache_context`, `mbedtls_ssl_cookie_context`, `mbedtls_ssl_ticket_context`, and the heap struct in `memory_buffer_alloc.c` — each guards that one context/struct's mutable state against concurrent calls from application-created threads sharing the same object.

But again — none of that runs by default. Out of the box, mbedtls is a single-threaded library that trusts the caller not to share state across threads.
