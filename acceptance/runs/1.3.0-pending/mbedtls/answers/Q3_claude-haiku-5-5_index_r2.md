## Short answer

Library code never calls `calloc` or `free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, and what those resolve to is decided by build configuration. A project substitutes its allocator either at compile time (macros) or at runtime (a function-pointer setter).

## What gets called

```
library code
  └─ mbedtls_calloc(n, sz)  ──┐  (platform.h: macro or extern, per config)
                              ▼
   ┌─ MBEDTLS_PLATFORM_MEMORY undefined ──► libc calloc / free (macro)
   ├─ MEMORY + CALLOC_MACRO + FREE_MACRO ─► your functions (macro, link-time)
   └─ MEMORY only ─► platform.c: mbedtls_calloc_func / mbedtls_free_func
                      (function pointers, default = STD_CALLOC/STD_FREE,
                       swapped at runtime by mbedtls_platform_set_calloc_free)
```

The mapping is in `include/mbedtls/platform.h:138-168`:

- **No `MBEDTLS_PLATFORM_MEMORY`:** `mbedtls_calloc` is `calloc` and `mbedtls_free` is `free`.
- **`MBEDTLS_PLATFORM_MEMORY` with both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`:** the macros expand to your symbols. No runtime hook exists in this mode.
- **`MBEDTLS_PLATFORM_MEMORY` alone:** `mbedtls_calloc` and `mbedtls_free` are real functions in `library/platform.c:47-55`. They dispatch through two static pointers, `mbedtls_calloc_func` and `mbedtls_free_func`, which start at `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`.

## How a project substitutes its allocator

**Option A: compile time.** Set `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`, typically through `-D` or a user config header that replaces `mbedtls_config.h`. Define `my_calloc` and `my_free` with matching signatures. The config doc says the two macros must be defined or undefined together (`mbedtls_config.h:197-198`).

**Option B: runtime.** Set `MBEDTLS_PLATFORM_MEMORY` and leave both macros undefined. Then call once, before any library allocation:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

With no default configured, the pointers start as `platform_calloc_uninit`, which returns NULL, and `platform_free_uninit`, which does nothing (`platform.c:25-42`). Until you call the setter, every library allocation fails.

**Option C: default override.** Keep the runtime setter but change the defaults with `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. These are documented in `mbedtls_config.h:4113-4134`.

## What the library does with the facility

- **Every allocation site uses the wrapper.** The index shows `mbedtls_calloc` called from roughly 130 functions across `library/` (cipher wrappers, bignum, ECP, PK, X.509, SSL, PSA) and `mbedtls_free` from a similar set. A grep of `library/` for raw `calloc(`/`free(` finds only one raw `free`, at `memory_buffer_alloc.c:404`. That frees the `backtrace_symbols()` array in the memory-debug path, not a library allocation.
- **The library ships one allocator of its own.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) carves allocations out of a caller-supplied buffer. It works by calling `mbedtls_platform_set_calloc_free` with its own functions, which are mutex-wrapped when `MBEDTLS_THREADING_C` is on. This is the same facility a project would use, so it is process-global. Whichever setter ran last wins, and a project cannot combine its own allocator with this one.

## Caveats

- I verified the mapping and the call chain from the index and the source. I did not check every call site individually.
- Thread safety of a custom allocator is not spelled out in the code I read. If threading is enabled, the mutex-wrapped path shows the library expects its allocator functions to be safe to call from multiple threads, so a custom allocator should be too.