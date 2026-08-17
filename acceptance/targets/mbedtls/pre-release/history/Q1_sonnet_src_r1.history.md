# Q1 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Grep`
- **asked:** pattern=mbedtls_threading_mutex|MBEDTLS_THREADING, path=~/ddb-targets/mbedtls
- **got:** Found 59 files ~/ddb-targets/mbedtls/tests/suites/test_suite_rsa.function ~/ddb-targets/mbedtls/tests/suites/test_suite_psa_crypto_entropy.function ~/ddb-targets/mbedtls/tests/suites/test_suite_psa_crypto_init.function ~…

### 2. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/threading.h
### 3. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/threading.c
- **got:** 1	/** 2	 * \file threading.h 3	 * 4	 * \brief Threading abstraction layer 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 9	 */ 10	#ifndef MBEDTLS_THREAD…

- **got:** 1	/* 2	 *  Threading abstraction layer 3	 * 4	 *  Copyright The Mbed TLS Contributors 5	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 6	 */ 7	 8	/* 9	 * Ensure gmtime_r is available even with -std=c99; must…

### 4. `Grep`
- **asked:** pattern=mbedtls_mutex_(lock|unlock), path=~/ddb-targets/mbedtls/library
- **got:** ~/ddb-targets/mbedtls/library/ssl_cache.c:84:    if ((ret = mbedtls_mutex_lock(&cache->mutex)) != 0) { ~/ddb-targets/mbedtls/library/ssl_cache.c:105:    if (mbedtls_mutex_unlock(&cache->mutex) != 0) { ~/ddb-targets/mbedt…

### 5. `Bash`
- **asked:** command=grep -n "MBEDTLS_THREADING_PTHREAD\|MBEDTLS_THREADING_ALT\|MBEDTLS_THREADING_C" ~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 274: * if MBEDTLS_THREADING_C is enabled. We recommend that calls from outside the 1879: *       #MBEDTLS_THREADING_C, even if individual TLS contexts are not 2165: * \def MBEDTLS_THREADING_ALT 2181: * Requires: MBEDTLS_…

### 6. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/threading_internal.h
- **got:** 1	/** 2	 * \file threading_internal.h 3	 * 4	 * \brief Threading interfaces used by the test framework 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 9	…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/rsa.c
- **got:** 1225	                       const unsigned char *input, 1226	                       unsigned char *output) 1227	{ 1228	    int ret = MBEDTLS_ERR_ERROR_CORRUPTION_DETECTED; 1229	    size_t olen; 1230	    mbedtls_mpi T; 12…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 2160	 * Uncomment to enable invasive tests. 2161	 */ 2162	//#define MBEDTLS_TEST_HOOKS 2163	 2164	/** 2165	 * \def MBEDTLS_THREADING_ALT 2166	 * 2167	 * Provide your own alternate implementation of threading primitives 2…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 3735	 * This module is required for SSL/TLS. 3736	 */ 3737	#define MBEDTLS_SSL_TLS_C 3738	 3739	/** 3740	 * \def MBEDTLS_THREADING_C 3741	 * 3742	 * Enable the threading abstraction layer. 3743	 * 3744	 * Traditionally, …

**Reasoning.** I now have enough to give a complete, well-cited answer.

## Answer

Yes — mbedtls has a full threading/mutex abstraction layer, gated behind an opt-in build option, used to protect a specific set of shared/global state.

**1. It's opt-in, off by default**

`MBEDTLS_THREADING_C` enables the abstraction layer and is commented out (disabled) by default: `include/mbedtls/mbedtls_config.h:3787`. Its doc comment (`include/mbedtls/mbedtls_config.h:3740-3786`) explains it must be turned on any time contexts/PSA state are shared across threads (any PSA call, any TLS/X.509/PK call when `MBEDTLS_USE_PSA

---

## Final answer as submitted

I now have enough to give a complete, well-cited answer.

## Answer

Yes — mbedtls has a full threading/mutex abstraction layer, gated behind an opt-in build option, used to protect a specific set of shared/global state.

**1. It's opt-in, off by default**

`MBEDTLS_THREADING_C` enables the abstraction layer and is commented out (disabled) by default: `include/mbedtls/mbedtls_config.h:3787`. Its doc comment (`include/mbedtls/mbedtls_config.h:3740-3786`) explains it must be turned on any time contexts/PSA state are shared across threads (any PSA call, any TLS/X.509/PK call when `MBEDTLS_USE_PSA_CRYPTO` is set, any TLS 1.3 connection, etc.).

Once enabled, you must pick one concrete mutex backend:
- `MBEDTLS_THREADING_PTHREAD` — wraps POSIX `pthread_mutex_t` (`include/mbedtls/mbedtls_config.h:2188-2196`).
- `MBEDTLS_THREADING_ALT` — lets the application supply its own mutex implementation via a `threading_alt.h` header and `mbedtls_threading_set_alt()` (`include/mbedtls/mbedtls_config.h:2165-2185`).

**2. The abstraction itself**

`include/mbedtls/threading.h` defines `mbedtls_threading_mutex_t`:
- Under pthreads it's a struct wrapping `pthread_mutex_t` plus a debug-only `state` byte (`include/mbedtls/threading.h:29-39`).
- Under `MBEDTLS_THREADING_ALT` the type comes from the user's `threading_alt.h` (`include/mbedtls/threading.h:42-44`).

Four global function pointers do all locking: `mbedtls_mutex_init/free/lock/unlock` (`include/mbedtls/threading.h:111-114`). `library/threading.c` provides the pthread implementations (`threading_mutex_init_pthread` etc., `library/threading.c:51-104`), wired to the pointers at file scope (`library/threading.c:101-104`). For the ALT case, `mbedtls_threading_set_alt()` swaps the four pointers to caller-supplied functions and eagerly initializes the global mutexes (`library/threading.c:133-154`); before that call the pointers default to stub functions that always fail (`library/threading.c:113-129`), so using the library before setting the alt implementation is safe-but-broken rather than undefined.

**3. What actually gets locked**

Global mutexes, declared in `include/mbedtls/threading.h:119-159` and defined in `library/threading.c:181-191`:
- `mbedtls_threading_readdir_mutex` — guards `readdir()` in `mbedtls_x509_crt_parse_path()`, since POSIX `readdir` isn't thread-safe (`library/x509_crt.c:1611-1660`).
- `mbedtls_threading_gmtime_mutex` — guards the fallback (non-`_r`) `gmtime()` call inside `mbedtls_platform_gmtime_r()` (`library/platform_util.c:189-201`).
- `mbedtls_threading_key_slot_mutex`, `mbedtls_threading_psa_globaldata_mutex`, `mbedtls_threading_psa_rngdata_mutex` — three separate PSA-subsystem locks, each documented in `include/mbedtls/threading.h:133-159` as guarding a specific slice of PSA global state (key-slot readers/state, other global_data fields, and the RNG state respectively). Used extensively throughout `library/psa_crypto.c` (e.g. `psa_crypto.c:131-165`, `:1310-1421`, `:2022-2045`, `:8030-8593`) and `library/psa_crypto_slot_management.c` (e.g. lines 200-206, 822-1090), plus `library/psa_crypto_random.c:147-154`.

Per-context mutexes (embedded directly in a struct, `#if defined(MBEDTLS_THREADING_C)`), each protecting that one context's mutable state so a single context can be safely shared across threads:
- `mbedtls_rsa_context.mutex` — locked around `mbedtls_rsa_public()` and the private-key operation (`library/rsa.c:1239-1260`, `:1518-1631`), protecting blinding state.
- `mbedtls_ctr_drbg_context.mutex` — around DRBG reseed/random generation (`library/ctr_drbg.c:703-711`).
- `mbedtls_hmac_drbg_context.mutex` — same idea (`library/hmac_drbg.c:388-396`).
- `mbedtls_entropy_context.mutex` — around entropy gather/update operations (`library/entropy.c:93-374`, four lock/unlock pairs).
- `mbedtls_ssl_cache_context.mutex` — around cache get/set/resize (`library/ssl_cache.c:84-362`).
- `mbedtls_ssl_ticket_context.mutex` — around ticket write/parse (`library/ssl_ticket.c:330-524`).
- `mbedtls_ssl_cookie_ctx.mutex` — around cookie write/check (`library/ssl_cookie.c:249-344`).
- `heap.mutex` in the debug memory-buffer allocator — around the global heap alloc/free path (`library/memory_buffer_alloc.c:544-562`).

**4. The locking pattern**

Uniform idiom everywhere: `if ((ret = mbedtls_mutex_lock(&x->mutex)) != 0) return ret;` ... critical section ... `if (mbedtls_mutex_unlock(&x->mutex) != 0) return MBEDTLS_ERR_THREADING_MUTEX_ERROR;` (e.g. `library/rsa.c:1239-1260`). Lock/unlock failures return `MBEDTLS_ERR_THREADING_MUTEX_ERROR` (`include/mbedtls/threading.h:25`) or `MBEDTLS_ERR_THREADING_BAD_INPUT_DATA` (`include/mbedtls/threading.h:23`) for a NULL mutex pointer (`library/threading.c:75-99`). All of this code is compiled only `#if defined(MBEDTLS_THREADING_C)` — with the feature off, there is no locking at all and the library assumes single-threaded use or externally-synchronized context sharing.

The library also documents that a separate helper for testing thread safety lives in the companion test framework (`framework/tests/src/threading_helpers.c`, referenced in comments at `include/mbedtls/threading.h:33` and `library/threading.c:62`), but that file itself is outside this repo's `library/`/`include/` tree (not fetched — see Gaps).

## Gaps

- `framework/tests/src/threading_helpers.c` is referenced by comments (`include/mbedtls/threading.h:32-36`, `library/threading.c:57-62`) as the place mutex `state` is checked, but I did not locate/open that file in this tree — it may live in a separate framework submodule not fully explored.
- `library/psa_crypto_core.h` and `docs/architecture/psa-thread-safety/psa-thread-safety.md` (both matched the initial grep) were not read in detail; they likely contain more design rationale for the three PSA mutexes but weren't needed to answer where/how locking occurs.
- Did not enumerate every single lock/unlock call site in `psa_crypto.c`/`psa_crypto_slot_management.c` (there are ~40+) — cited representative ranges rather than all of them.
