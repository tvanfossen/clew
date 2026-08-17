# Q1 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll search the mbedtls codebase for mutex and locking mechanisms.

### 1. `Bash`
- **asked:** command=cd ~/ddb-targets/mbedtls && find . -type f -name "*.h" -o -name "*.c" | head -20
- **got:** ./tests/src/certs.c ./tests/src/psa_test_wrappers.c ./tests/src/test_helpers/ssl_helpers.c ./tests/configs/config_test_driver.h ./tests/configs/user-config-zeroize-memset.h ./tests/configs/user-config-malloc-0-null.h ./t…

### 2. `Grep`
- **asked:** pattern=mutex|lock
- **got:** Found 132 files tests/src/test_helpers/ssl_helpers.c tests/include/test/ssl_helpers.h tests/include/alt-dummy/threading_alt.h programs/test/benchmark.c programs/ssl/ssl_test_lib.c programs/ssl/ssl_client2.c programs/ssl/…

### 3. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/threading.h
- **got:** 1	/** 2	 * \file threading.h 3	 * 4	 * \brief Threading abstraction layer 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 9	 */ 10	#ifndef MBEDTLS_THREAD…

### 4. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/threading.c
- **got:** 1	/* 2	 *  Threading abstraction layer 3	 * 4	 *  Copyright The Mbed TLS Contributors 5	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 6	 */ 7	 8	/* 9	 * Ensure gmtime_r is available even with -std=c99; must…

### 5. `Grep`
- **asked:** pattern=mbedtls_mutex_lock|mbedtls_mutex_unlock
- **got:** include/mbedtls/threading.h:113:extern int (*mbedtls_mutex_lock)(mbedtls_threading_mutex_t *mutex); include/mbedtls/threading.h:114:extern int (*mbedtls_mutex_unlock)(mbedtls_threading_mutex_t *mutex); library/platform_u…

### 6. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/psa_crypto.c
- **got:** 125	 126	static uint8_t psa_get_initialized(void) 127	{ 128	    uint8_t initialized; 129	 130	#if defined(MBEDTLS_THREADING_C) 131	    mbedtls_mutex_lock(&mbedtls_threading_psa_rngdata_mutex); 132	#endif /* defined(MBEDT…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/ssl_cache.c
- **got:** 75	                          unsigned char const *session_id, 76	                          size_t session_id_len, 77	                          mbedtls_ssl_session *session) 78	{ 79	    int ret = MBEDTLS_ERR_ERROR_CORRUPT…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/ssl_cache.h
- **got:** 1	/** 2	 * \file ssl_cache.h 3	 * 4	 * \brief SSL session cache implementation 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 9	 */ 10	#ifndef MBEDTLS_S…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/platform_util.c
- **got:** 180	    /* MSVC and mingw64 argument order and return value are inconsistent with the C11 standard */ 181	    return (gmtime_s(tm_buf, tt) == 0) ? tm_buf : NULL; 182	#endif 183	#elif !defined(PLATFORM_UTIL_USE_GMTIME) 18…

### 10. `Grep`
- **asked:** pattern=mbedtls_threading_key_slot_mutex
- **got:** docs/architecture/psa-thread-safety/psa-thread-safety.md:184:The key store is protected by a single global mutex `mbedtls_threading_key_slot_mutex`. docs/architecture/psa-thread-safety/psa-thread-safety.md:186:We maintai…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/architecture/psa-thread-safety/psa-thread-safety.md
- **got:** 1	# Thread-safety of the PSA subsystem 2	 3	Currently, PSA Crypto API calls in Mbed TLS releases are not thread-safe. 4	 5	As of Mbed TLS 3.6, an MVP for making the [PSA Crypto key management API](https://arm-software.gi…

### 12. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/psa_crypto_random.c
- **got:** 140	{ 141	#if defined(MBEDTLS_PLATFORM_IS_UNIXLIKE) 142	    intmax_t pid = getpid(); 143	    if (pid != rng->pid) { 144	        /* This is a (grand...)child of the original process, but 145	         * we inherited the RN…

**Reasoning.** Yes, mbedtls **does use mutexes extensively** for thread-safe access to shared resources. Here's where and how:

## Threading Architecture

mbedtls provides a threading abstraction layer with a pluggable implementation (`include/mbedtls/threading.h:27-103`). The default implementation uses POSIX pthread mutexes when `MBEDTLS_THREADING_PTHREAD` is defined.

## Global Mutexes

The library defines several **global mutexes** (`include/mbedtls/threading.h:105-159`):

1. **`mbedtls_threading_readdir_mutex`** (`include/mbedtls/threading.h:120`) — Protects directory reading operations when `MBEDTLS_FS

---

## Final answer as submitted

Yes, mbedtls **does use mutexes extensively** for thread-safe access to shared resources. Here's where and how:

## Threading Architecture

mbedtls provides a threading abstraction layer with a pluggable implementation (`include/mbedtls/threading.h:27-103`). The default implementation uses POSIX pthread mutexes when `MBEDTLS_THREADING_PTHREAD` is defined.

## Global Mutexes

The library defines several **global mutexes** (`include/mbedtls/threading.h:105-159`):

1. **`mbedtls_threading_readdir_mutex`** (`include/mbedtls/threading.h:120`) — Protects directory reading operations when `MBEDTLS_FS_IO` is enabled.

2. **`mbedtls_threading_gmtime_mutex`** (`include/mbedtls/threading.h:130`) — Protects calls to the non-reentrant `gmtime()` function. Used in `library/platform_util.c:189-201` to serialize access when `MBEDTLS_HAVE_TIME_DATE` is enabled without a thread-safe alternative.

3. **PSA Crypto Mutexes** (`include/mbedtls/threading.h:133-159`):
   - **`mbedtls_threading_key_slot_mutex`** — Protects the key store (`global_data.key_slots`), key slot state transitions, and reader registration. Used throughout `library/psa_crypto.c` and `library/psa_crypto_slot_management.c`.
   - **`mbedtls_threading_psa_globaldata_mutex`** — Protects general PSA global data and initialization state.
   - **`mbedtls_threading_psa_rngdata_mutex`** — Protects PSA RNG state and data.

## Per-Context Mutexes

The SSL session cache includes a per-context mutex (`include/mbedtls/ssl_cache.h:71-72`) embedded in `mbedtls_ssl_cache_context`. This is locked during cache get/set/remove operations (`library/ssl_cache.c:84-86` and `library/ssl_cache.c:259`).

## How the Locking Works

**Function pointer pattern:** The library uses function pointers initialized at runtime (`library/threading.c:101-104`):
```c
void (*mbedtls_mutex_init)(mbedtls_threading_mutex_t *) = threading_mutex_init_pthread;
void (*mbedtls_mutex_free)(mbedtls_threading_mutex_t *) = threading_mutex_free_pthread;
int (*mbedtls_mutex_lock)(mbedtls_threading_mutex_t *) = threading_mutex_lock_pthread;
int (*mbedtls_mutex_unlock)(mbedtls_threading_mutex_t *) = threading_mutex_unlock_pthread;
```

**Pthread implementation** (`library/threading.c:50-99`):
- `threading_mutex_init_pthread()` calls `pthread_mutex_init()` (`library/threading.c:63`)
- `threading_mutex_lock_pthread()` calls `pthread_mutex_lock()` and returns `MBEDTLS_ERR_THREADING_MUTEX_ERROR` on failure (`library/threading.c:75-86`)
- `threading_mutex_unlock_pthread()` calls `pthread_mutex_unlock()` similarly (`library/threading.c:88-99`)

**Example usage** — PSA RNG access (`library/psa_crypto_random.c:147`):
```c
mbedtls_mutex_lock(&mbedtls_threading_psa_rngdata_mutex);
// ... access RNG state ...
mbedtls_mutex_unlock(&mbedtls_threading_psa_rngdata_mutex);
```

## Thread-Safety Scope

As documented in `docs/architecture/psa-thread-safety/psa-thread-safety.md:3-5`, **only the PSA Crypto key management API and `psa_crypto_init` are thread-safe as of Mbed TLS 3.6**. The mutex protection is conditional on `MBEDTLS_THREADING_C` being enabled.

## Alternative Implementations

Users can provide custom threading implementations via `mbedtls_threading_set_alt()` (`include/mbedtls/threading.h:94-97`) to use mutexes with non-pthread platforms.

## Gaps

- I did not trace all 40+ mutex lock/unlock call sites across the codebase, only verified the key ones.
- The exact contention characteristics and performance implications were not analyzed.
- Whether additional functions beyond key management will be made thread-safe in future versions is specification, not implementation.
