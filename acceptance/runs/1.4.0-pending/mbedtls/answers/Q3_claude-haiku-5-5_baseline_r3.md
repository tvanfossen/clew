**Short answer:** in a default build, `mbedtls_calloc` is just the C library's `calloc` and `mbedtls_free` is `free`. Only when `MBEDTLS_PLATFORM_MEMORY` is enabled does the library route allocations through a replaceable hook. The library never calls `malloc`/`calloc`/`free` directly outside the platform layer and its own buffer allocator.

**What gets called**

The library's allocation sites all call `mbedtls_calloc()` / `mbedtls_free()` (about 48 files, e.g. `bignum.c:218`, `ecp.c:1378`, `lms.c:507`). What those names resolve to depends on config, as set out in `include/mbedtls/platform.h:134-168`:

| Config | `mbedtls_calloc` / `mbedtls_free` |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (the default; the option is commented out in `mbedtls_config.h:208`) | macros for `calloc` / `free` |
| On, with both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` defined | macros for your functions, resolved at compile time |
| On, without those macros | real functions in `library/platform.c`, dispatching through function pointers |

In the third row, `platform.c:44-55` holds two static function pointers, initialised to `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`. `mbedtls_calloc()` and `mbedtls_free()` just call through them. If `MBEDTLS_PLATFORM_STD_CALLOC` is not defined, it falls back to `platform_calloc_uninit`, which returns NULL. So an unconfigured runtime hook fails every allocation rather than silently using a default.

**How a project substitutes its allocator**

Two options:

1. **Compile time.** Define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free` in the config. Both macros must be set together. No runtime hook is compiled in, and the macros are used directly.
2. **Runtime.** Define `MBEDTLS_PLATFORM_MEMORY` without the macros, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any allocation. Optionally set `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` to change the defaults, or set `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` so no libc symbols are referenced at all.

Your calloc must zero the memory, and `free(NULL)` must be a no-op. The config comments state these requirements at `mbedtls_config.h:4113-4133`.

**What the library does with the facility**

- **Its own allocator.** `library/memory_buffer_alloc.c` is a heap over a caller-supplied buffer. `mbedtls_memory_buffer_alloc_init()` (line 566) installs its own `buffer_alloc_calloc` / `buffer_alloc_free` (or mutex-wrapped variants when `MBEDTLS_THREADING_C` is on) through `mbedtls_platform_set_calloc_free`. `mbedtls_memory_buffer_alloc_free()` zeroes its state. The library uses the same hook to plug in its own allocator.
- **Uninitialised default.** The `platform_*_uninit` stubs make a missing configuration fail loudly (NULL from calloc) rather than fall back to libc silently.
- **Not a per-module override.** The hook is one global pair of pointers. Nothing in the library installs a different allocator per context, so the choice is global.

**Caveats I noticed (from reading, not testing)**

- `mbedtls_platform_set_calloc_free` is a plain pointer assignment with no synchronisation. It should be called before any threads start. I did not find any guard for this.
- The runtime path is compiled out if both macros are defined, so `mbedtls_memory_buffer_alloc_init` (which calls `mbedtls_platform_set_calloc_free`) would not link in that configuration. I did not build this to confirm it.