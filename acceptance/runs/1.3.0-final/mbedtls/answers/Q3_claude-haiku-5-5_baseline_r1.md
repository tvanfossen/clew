**Short answer:** mbedtls never calls `calloc` or `free` directly. Every allocation goes through `mbedtls_calloc(n, size)` and `mbedtls_free(ptr)`, and what those names resolve to depends on the build configuration. This repo is at `068ff08`. I verified everything below by reading the source; I did not build or run anything.

**What gets called**

The library code uses the `mbedtls_` names throughout. About 48 files in `library/` do (for example `ssl_msg.c` for handshake flight buffers and reassembly, `psa_crypto.c` with 16 sites, `bignum.c`, `ecp.c`). The one direct libc `free` is `memory_buffer_alloc.c:404`, which frees the `backtrace_symbols()` output, and that function's result is libc-allocated, so the pairing is correct.

Resolution depends on the config:

| Config | `mbedtls_calloc` / `mbedtls_free` become | Where |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | `calloc` / `free`, as macros | `platform.h:166-167` |
| `MBEDTLS_PLATFORM_MEMORY` on, both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `_FREE_MACRO` set | your macros, as compile-time aliases | `platform.h:138-144` |
| `MBEDTLS_PLATFORM_MEMORY` on, no macros | real functions that call through two global function pointers | `platform.c:44-63` |

In the third row the pointers default to `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE`. Those default to libc `calloc` and `free` when the std functions are available. Otherwise they are stubs: calloc returns NULL and free does nothing (`platform.c:25-42`).

**How a project substitutes its allocator**

Option A, compile time, zero indirection:
- In your user config, define `MBEDTLS_PLATFORM_C`, `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`. Both macros must be set together.
- Make sure `my_calloc` and `my_free` are declared in every translation unit that uses them. `platform.h` does not include your header, so check how your config exposes it.

Option B, runtime, one call at startup:
- Define only `MBEDTLS_PLATFORM_MEMORY`.
- Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (declared at `platform.h:160`) before any other mbedtls call.
- The setter is a plain store with no locking or validation (`platform.c:57-63`). Call it before threads start.
- The header says a non-null pointer passed to free must have come from your calloc and not already be freed. Mixing allocators is undefined.
- The code shows no way to migrate objects already allocated, so swap before creating any mbedtls context.

**What the library does with the facility itself**

`library/memory_buffer_alloc.c` is a built-in arena allocator for systems with no heap. `mbedtls_memory_buffer_alloc_init(buf, len)` carves allocations out of a caller-supplied buffer. It installs its own pair through the runtime setter (`memory_buffer_alloc.c:572-575`), which is Option B used by the library on itself. Other details:

- With `MBEDTLS_THREADING_C`, the installed functions wrap the heap in a mutex (`:541-563`). If the lock fails, `free` silently drops the request, which the code comments call preferable to heap corruption. If the unlock fails, `calloc` returns NULL and leaks the block.
- Its debug options record a backtrace per block (`:281-283`, `:347-349`), and `mbedtls_free` aborts with a message on unallocated or out-of-arena pointers (`:373`, `:390`).

**Practical takeaway:** for a bare-metal or RTOS port, Option A is the zero-overhead choice. Option B suits a project that picks its allocator at runtime, provided the setter runs first.