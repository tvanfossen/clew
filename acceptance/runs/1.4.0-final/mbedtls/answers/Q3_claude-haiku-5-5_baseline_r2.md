**Short answer:** Every allocation in the library goes through two internal names, `mbedtls_calloc` and `mbedtls_free`. By default they forward to the C library's `calloc` and `free`. A project can replace them at compile time with macros, or at runtime with `mbedtls_platform_set_calloc_free()`. Nothing else in `library/` calls libc allocation directly.

**What gets called**

- **Default (`MBEDTLS_PLATFORM_MEMORY` off):** `include/mbedtls/platform.h:163-167` defines `mbedtls_calloc` as `calloc` and `mbedtls_free` as `free` as plain macros. There is no indirection.
- **`MBEDTLS_PLATFORM_MEMORY` on:** `library/platform.c:44-55` holds two function pointers, initialised to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. `mbedtls_calloc()` and `mbedtls_free()` are real functions that call through those pointers.
- **No standard functions (`MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`):** the defaults become `platform_calloc_uninit` (always returns NULL) and `platform_free_uninit` (does nothing), so an unconfigured build fails allocations cleanly rather than linking against `calloc`. (`platform.c:24-42`)

**How a project substitutes its allocator**

Option A, compile time (no indirection, fastest):
1. Enable `MBEDTLS_PLATFORM_MEMORY` in its config.
2. Define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. They must be defined together (`mbedtls_config.h:197-198`).
3. `platform.h:138-145` then aliases `mbedtls_calloc`/`mbedtls_free` to those macros, and `platform.c` compiles out its runtime machinery.

Option B, runtime:
1. Enable `MBEDTLS_PLATFORM_MEMORY` without the two macros. Optionally set `MBEDTLS_PLATFORM_STD_CALLOC`/`_FREE` to change the defaults.
2. Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other Mbed TLS call. The setter is a plain pointer assignment with no lock (`platform.c:57-63`), so calling it while other threads use the library is a race.

The contract the replacement must honour is in `mbedtls_config.h:4113-4133`:
- `calloc` must zero the returned memory and return NULL on failure.
- `free` must accept NULL.
- `free` only receives pointers that came from the matching `calloc`.

**What the library does with the facility**

- **Everything routes through it.** About 50 `library/*.c` files call `mbedtls_calloc` or `mbedtls_free`, roughly 170 and 190 call sites respectively. The only raw libc allocation in `library/` is the default in `platform.c` itself, plus a `free(hdr->trace)` in the buffer allocator's debug path.
- **Secure cleanup.** `mbedtls_zeroize_and_free()` (`library/platform_util.c:139-146`) zeroes the buffer and then calls `mbedtls_free`. Key and secret buffers use this, so the zeroing happens on the same path whichever allocator is installed.
- **A built-in allocator plugs into the same hook.** `library/memory_buffer_alloc.c:566-576`, `mbedtls_memory_buffer_alloc_init()`, carves allocations out of a caller-supplied static buffer. It does this by calling `mbedtls_platform_set_calloc_free()` itself, so it is one more client of the same substitution mechanism. Its `_mutexed` variants take the library mutex when `MBEDTLS_THREADING_C` is on. The programs under `programs/ssl/` and `programs/test/` use it this way.

**Consequences to watch for**

- Since `memory_buffer_alloc_init()` swaps the global pointers, it silently overrides any allocator set earlier. Only one allocator is active at a time.
- Because the pointers are global, two independent allocators in one process cannot coexist. The setter is the only switch.
- Using `MBEDTLS_PLATFORM_MEMORY` is a prerequisite for runtime substitution, but not for the compile-time macro path. The two options are mutually exclusive: when both macros are defined, the runtime setter is compiled out.