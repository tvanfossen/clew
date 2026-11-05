**Short answer:** every library allocation goes through `mbedtls_calloc()` / `mbedtls_free()`. Those are either thin macros over libc `calloc`/`free`, or wrappers that call function pointers. A project can replace them at compile time or at run time. The library's own stack-based allocator uses the same hook to install itself.

**Call path (default build)**

```
library code
  └─ mbedtls_calloc(n, size)            include/mbedtls/platform.h
       └─ (*mbedtls_calloc_func)(n, size)   library/platform.c:47-50
            └─ mbedtls_calloc_func, initialised to MBEDTLS_PLATFORM_STD_CALLOC   platform.c:44
```

`mbedtls_free` mirrors this through `mbedtls_free_func` (`platform.c:52-55`). The index shows about 147 callers of `mbedtls_calloc` and 133 of `mbedtls_free`, including cipher contexts, ASN.1, ECP and SSL.

**Compile-time substitution**

`platform.h` has two branches. The index gates them on `MBEDTLS_PLATFORM_MEMORY`:

- **Macros defined** (`MBEDTLS_PLATFORM_MEMORY` on): `mbedtls_calloc` expands to `MBEDTLS_PLATFORM_CALLOC_MACRO` (`platform.h:144`), and `mbedtls_free` expands to `MBEDTLS_PLATFORM_FREE_MACRO` (`platform.h:143`). The wrapper functions in `platform.c` are compiled out. Calls go straight to your functions.
- **Macros not defined** (default): `mbedtls_calloc` / `mbedtls_free` expand to plain `calloc` / `free` (`platform.h:166-167`), and the function-pointer path above is used.

To substitute at build time, a project sets `MBEDTLS_PLATFORM_MEMORY` in its user config (`MBEDTLS_USER_CONFIG_FILE`) and defines `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to its allocator names. The index has no definition site for either macro, which is consistent with them being supplied by the project. The index also contains a test config, `tests/configs/user-config-malloc-0-null.h`, that sets `MBEDTLS_PLATFORM_MEMORY`.

**Run-time substitution**

`mbedtls_platform_set_calloc_free(calloc_func, free_func)` (`platform.c:57-63`) just assigns the two globals and returns 0. It has no locking and no NULL checks. It is only available in the function-pointer branch, so it must be called before any threads start and before any memory is allocated.

**What the library does with the facility**

`mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) is the library's own allocator. It:

1. Zeroes its global heap context.
2. Initialises the mutex if `MBEDTLS_THREADING_C` is set.
3. Calls `mbedtls_platform_set_calloc_free()` with `buffer_alloc_calloc_mutexed` / `buffer_alloc_free_mutexed`, or the unmutexed pair. This overwrites whatever allocator the project had installed.
4. Aligns the caller's buffer to `MBEDTLS_MEMORY_ALIGN_MULTIPLE`, zeroes it, and writes one free block with magic headers.

`buffer_alloc_calloc` rejects `n*size` overflow, rounds up to alignment, and does a first-fit search of the free list. It returns NULL when no block fits. With `MBEDTLS_MEMORY_BACKTRACE` it also records backtraces.

**Things to watch**

- **Ordering:** calling `mbedtls_memory_buffer_alloc_init` replaces any allocator set earlier with `mbedtls_platform_set_calloc_free`. Calling it after a custom setter silently discards that setter.
- **Failed init:** if `len` is too small, `mbedtls_memory_buffer_alloc_init` still installs the hooks but returns before setting up the heap. Every later allocation then returns NULL.
- **Not verified:** I could not read the `#if` chain at `platform.c:20-64` or find where `MBEDTLS_PLATFORM_STD_CALLOC` is defined, because the index holds no definition site for it. I am inferring from the gate layout that the default branch uses libc `calloc`/`free`.