# Q10 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=cd ~/ddb-targets/mbedtls && find . -maxdepth 2 -type d | head -50
- **got:** . ./scripts ./scripts/maintainer ./scripts/data_files ./framework ./.github ./.github/ISSUE_TEMPLATE ./pkgconfig ./tests ./tests/src ./tests/scripts ./tests/opt-testcases ./tests/suites ./tests/configs ./tests/git-script…

### 2. `Grep`
- **asked:** pattern=^static\s+\w[\w\s\*]*\b\w+\s*(=|;)\s*$, path=~/ddb-targets/mbedtls/library
- **got:** Found 9 files library/ssl_tls.c library/sha256.c library/sha512.c library/psa_crypto_slot_management.c library/psa_crypto.c library/memory_buffer_alloc.c library/hmac_drbg.c library/ctr_drbg.c library/ecp.c

### 3. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/memory_buffer_alloc.c
- **got:** 1	/* 2	 *  Buffer-based memory allocator 3	 * 4	 *  Copyright The Mbed TLS Contributors 5	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 6	 */ 7	 8	#include "common.h" 9	 10	#if defined(MBEDTLS_MEMORY_BUFFER…

### 4. `Bash`
- **asked:** command=grep -n "global_data\|^static.*global" library/psa_crypto_slot_management.c | head -30
- **got:** 155:/* In global_data.first_free_slot_index, use this special value to 191:} psa_global_data_t; 193:static psa_global_data_t global_data; 203:    initialized = global_data.key_slots_initialized; 283:    psa_key_slot_t *s…

### 5. `Grep`
- **asked:** pattern=^static\s+\w[\w\s\*]*\b\w+\s*(=|;)\s*$, path=~/ddb-targets/mbedtls/library/sha256.c
- **got:** 174:static jmp_buf return_from_sigill;

### 6. `Bash`
- **asked:** command=grep -n "^static\|initialized\|K\[\]\|s_prime" library/sha256.c | head -20
- **got:** 143:static int mbedtls_a64_crypto_sha256_determine_support(void) 148:static int mbedtls_a64_crypto_sha256_determine_support(void) 153:static int mbedtls_a64_crypto_sha256_determine_support(void) 164:static int mbedtls_a6…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/sha256.c
- **got:** 160	#endif 161	#include <Windows.h> 162	#include <processthreadsapi.h> 163	 164	static int mbedtls_a64_crypto_sha256_determine_support(void) 165	{ 166	    return IsProcessorFeaturePresent(PF_ARM_V8_CRYPTO_INSTRUCTIONS_AV…

### 8. `Bash`
- **asked:** command=grep -n "^static.*;$\|^static.*=.*;$" library/ecp.c | grep -v "^.*(.*).*;" | head -20 echo --- grep -n "mbedtls_ecp_grp_id_list\|static.*curve" library/ecp.c | head -10
- **got:** 89:static unsigned long add_count, dbl_count; 91:static unsigned long mul_count; 105:static unsigned ecp_max_ops = 0; 393:static mbedtls_ecp_group_id ecp_supported_grp_id[ECP_NB_CURVES]; --- 346:static const mbedtls_ecp_…

### 9. `Bash`
- **asked:** command=grep -n "ecp_max_ops\|MBEDTLS_ECP_BUDGET\|mbedtls_ecp_set_max_ops" library/ecp.c | head -20
- **got:** 99: * Note that regardless of the value of ecp_max_ops, always at 102: * Setting ecp_max_ops=1 can be suitable for testing purposes 105:static unsigned ecp_max_ops = 0; 108: * Set ecp_max_ops 110:void mbedtls_ecp_set_max…

**Reasoning.** Good, this confirms enough detail. I have three solid, verified couplings. Composing final answer.

## Answer

Three couplings found where one function writes shared (static/global) state and a different function later reads it, with no direct call edge connecting the writer to the reader:

### 1. `mbedtls_memory_buffer_alloc_init()` → `buffer_alloc_calloc()` / `buffer_alloc_free()` (heap allocator state)

- Shared state: `static buffer_alloc_ctx heap;` — `library/memory_buffer_alloc.c:68`
- Writer: `mbedtls_memory_buffer_alloc_init()` sets `heap.buf`, `heap.len`, `heap.first`, `heap.first_fre

---

## Final answer as submitted

Good, this confirms enough detail. I have three solid, verified couplings. Composing final answer.

## Answer

Three couplings found where one function writes shared (static/global) state and a different function later reads it, with no direct call edge connecting the writer to the reader:

### 1. `mbedtls_memory_buffer_alloc_init()` → `buffer_alloc_calloc()` / `buffer_alloc_free()` (heap allocator state)

- Shared state: `static buffer_alloc_ctx heap;` — `library/memory_buffer_alloc.c:68`
- Writer: `mbedtls_memory_buffer_alloc_init()` sets `heap.buf`, `heap.len`, `heap.first`, `heap.first_free` — `library/memory_buffer_alloc.c:590-599`
- Reader: `buffer_alloc_calloc()` reads `heap.buf`, `heap.first`, `heap.first_free` to service an allocation — `library/memory_buffer_alloc.c:201,210`
- Reader: `buffer_alloc_free()` reads/mutates the same fields — `library/memory_buffer_alloc.c:367,371,472-477`
- No call edge: `mbedtls_memory_buffer_alloc_init()` never calls `buffer_alloc_calloc`/`buffer_alloc_free` directly. It registers them as function pointers via `mbedtls_platform_set_calloc_free(buffer_alloc_calloc, buffer_alloc_free)` — `library/memory_buffer_alloc.c:575` (or the mutexed variants, `library/memory_buffer_alloc.c:572-573`). The reader functions are invoked later, indirectly, whenever unrelated code calls `mbedtls_calloc()`/`mbedtls_free()`, which dereference the stored pointer at runtime — not a static call from `init`.

### 2. `mbedtls_a64_crypto_sha256_determine_support()` → `sigill_handler()` (via `return_from_sigill`)

- Shared state: `static jmp_buf return_from_sigill;` — `library/sha256.c:174`
- Writer: `mbedtls_a64_crypto_sha256_determine_support()` calls `setjmp(return_from_sigill)`, populating the buffer — `library/sha256.c:202`
- Reader: `sigill_handler()` calls `longjmp(return_from_sigill, 1)` to unwind back into the point saved by `setjmp` — `library/sha256.c:182`
- No call edge: `sigill_handler` is registered as a `SIGILL` signal handler (`sa_handler = sigill_handler`, `library/sha256.c:196`, installed at `library/sha256.c:198`) and is invoked asynchronously by the OS on an illegal-instruction trap, not called by `determine_support`.

### 3. `mbedtls_ecp_set_max_ops()` → `MBEDTLS_ECP_BUDGET` check sites (op-count budget)

- Shared state: `static unsigned ecp_max_ops = 0;` — `library/ecp.c:105`
- Writer: `mbedtls_ecp_set_max_ops(unsigned max_ops)` sets `ecp_max_ops = max_ops;` — `library/ecp.c:110-112`
- Readers: numerous EC arithmetic routines check `ecp_max_ops` via the `MBEDTLS_ECP_BUDGET` macro / direct read, e.g. `library/ecp.c:252,266-267`, and macro invocations at `library/ecp.c:1905,1936,1951,1976,2083,2200,2629,2836`
- No call edge: `mbedtls_ecp_set_max_ops` is a standalone public setter invoked once by application/library init code; it does not call any of the arithmetic functions that later check the budget — the coupling is purely through the static variable read at each restartable-operation checkpoint, at arbitrary later times.

## Gaps

- I did not exhaustively enumerate every static/global in the tree (`grep` was scoped to a handful of files that surfaced obvious module-level state: `ssl_tls.c`, `sha256.c`, `sha512.c`, `psa_crypto_slot_management.c`, `psa_crypto.c`, `memory_buffer_alloc.c`, `hmac_drbg.c`, `ctr_drbg.c`, `ecp.c`). Other files may contain similar decoupled read/write pairs I didn't inspect.
- I looked at `psa_crypto_slot_management.c`'s `global_data` (key-slot table) but did not trace its full call graph; its writer/reader functions (`psa_initialize_key_slots`, `psa_get_key_slot`, etc.) appeared to be linked by ordinary direct calls within the same module, so I did not report it as a "no call between them" case without more certainty — that needs a deeper call-graph trace to confirm or refute.
- "No call between them" was verified by reading each function body and confirming the connection is via a registered function pointer (`memory_buffer_alloc.c`) or an OS signal (`sha256.c`), and by confirming no call site exists between setter and checkers (`ecp.c`) within the files inspected — not via a full whole-program call-graph tool (none was available; source reading only).
