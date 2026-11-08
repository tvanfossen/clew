**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()`, and what those reach depends on build config. By default that is the C library. A project can substitute its own allocator at compile time with two macros, or at runtime with `mbedtls_platform_set_calloc_free()`. The library's own memory-buffer allocator uses that same runtime hook.

**Call chain**

```
library code (e.g. aes_ctx_alloc, ecp_mul_comb, asn1_get_sequence_of_cb)
   └─ mbedtls_calloc(n, size)            library/platform.c:47
        └─ (*mbedtls_calloc_func)(n, size)   file-static function pointer
             ├─ default: MBEDTLS_PLATFORM_STD_CALLOC (calloc, or an "uninit" stub that returns NULL)
             ├─ set at runtime by mbedtls_platform_set_calloc_free()
             └─ set by mbedtls_memory_buffer_alloc_init()
```

Free mirrors this: `mbedtls_free()` at `platform.c:52` calls `mbedtls_free_func`. `mbedtls_zeroize_and_free` and the `*_ctx_free` functions go through it too.

**Three configurations** (`include/mbedtls/platform.h:138-168`, documented at `mbedtls_config.h:154-207`)

| Config | What `mbedtls_calloc` becomes |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | `calloc` / `free`, macro-mapped in `platform.h:166` |
| `MBEDTLS_PLATFORM_MEMORY` on, `CALLOC_MACRO` + `FREE_MACRO` both defined | Your function or macro, **compile time**. The `mbedtls_calloc`/`mbedtls_free` names are `#define`d to it, so no function call is emitted. |
| `MBEDTLS_PLATFORM_MEMORY` on, macros not defined | Function-pointer dispatch, **runtime**. Default target is `MBEDTLS_PLATFORM_STD_CALLOC`/`STD_FREE` if you define them, else an "uninit" stub. Calloc returns NULL and free does nothing until you call `mbedtls_platform_set_calloc_free()`. |

`platform.c:16-22` says the compile-time macros take precedence. When both macros are set, the runtime setter and its pointers are compiled out entirely.

**How a project substitutes its allocator**

- **Compile time (preferred for embedded):** in your `mbedtls_config.h` override or via `-D`:
  ```c
  #define MBEDTLS_PLATFORM_MEMORY
  #define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc   /* void *(size_t, size_t) */
  #define MBEDTLS_PLATFORM_FREE_MACRO    my_free     /* void (void *) */
  ```
  Both macros must be defined together. Zeroing and NULL-on-failure are your responsibility, as the config comments require.
- **Runtime:** enable only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other library call. It always returns 0 and does no validation.
- **Or** define `MBEDTLS_PLATFORM_STD_CALLOC` / `STD_FREE` to change the default target without changing the macro path. `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` stops the library from assuming `calloc` exists at all.

**What the library does with the facility itself**

`library/memory_buffer_alloc.c` is a stack-based allocator over a caller-supplied buffer. `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566`):

1. Zeroes its static heap context.
2. If `MBEDTLS_THREADING_C` is on, inits a mutex and calls `mbedtls_platform_set_calloc_free(buffer_alloc_calloc_mutexed, buffer_alloc_free_mutexed)`. Otherwise it installs the unlocked variants.
3. Aligns the buffer, zeroes it, and writes the first block header with magic values.

So "library uses the facility" means this module is the only in-tree caller of `mbedtls_platform_set_calloc_free` according to the index. It hot-swaps the global allocator to point into the caller's buffer, and every library allocation then lands there. Callers can see this in `programs/test/benchmark.c`.

**Things to watch**

- `buffer_alloc_calloc_mutexed` (`memory_buffer_alloc.c:541`) returns NULL if the unlock fails, after it has already allocated. That block is lost. This is a minor edge, but it's a real leak path if the mutex misbehaves.
- The runtime pointers are plain globals with no synchronisation. Call the setter before any threads start, or the switch races with in-flight allocations.
- Because the setter is global, one `mbedtls_memory_buffer_alloc_init` affects every Mbed TLS context in the process. Use it only with one heap per process.

I didn't check every call site exhaustively. The caller list comes from the index, and the configuration reading comes from the header and `platform.c` as read.