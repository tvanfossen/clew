Inside the library, every allocation goes through `mbedtls_calloc()` and every release through `mbedtls_free()`. Those two names are not the libc functions unless you configure them that way. What they resolve to is decided at build time, and optionally changed at run time.

**What gets called**

With `MBEDTLS_PLATFORM_MEMORY` off (the default, per `include/mbedtls/mbedtls_config.h:208`), `platform.h:163-167` makes `mbedtls_calloc` a macro for `calloc` and `mbedtls_free` a macro for `free`. There is no indirection.

With `MBEDTLS_PLATFORM_MEMORY` on, there are three cases:

| Config | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` both defined | Those macros, directly (`platform.h:139-145`). `platform.c:20` omits all runtime machinery. |
| Neither macro defined | Real functions in `library/platform.c:47-55`. They call through two static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func` (`platform.c:44-45`). |
| Only one of the two macros defined | Not allowed. The config comment at `mbedtls_config.h:198` says both must be set or both unset. |

The function pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. If the config does not define those, they default to stubs (`platform.c:24-42`). The stub calloc returns NULL and the stub free does nothing. So a build with `MBEDTLS_PLATFORM_MEMORY` and no allocator configured fails every allocation until something sets one.

**How a project substitutes its allocator**

Two routes:

1. **Compile time.** Define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config (for example `MBEDTLS_USER_CONFIG_FILE`), with `MBEDTLS_PLATFORM_MEMORY` on. The macros expand to whatever the project wants, such as `my_calloc` and `my_free`. There is no runtime setter. The library's own `mbedtls_calloc` call sites just become direct calls to the project's functions.

2. **Run time.** Enable `MBEDTLS_PLATFORM_MEMORY` without the two macros, then call once at startup:
   ```c
   mbedtls_platform_set_calloc_free(my_calloc, my_free);
   ```
   `platform.c:57-63` stores the two pointers and returns 0. It has no locking, so call it before any other thread touches the library. Also, `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` can be set to the project's functions, which is the same as a built-in default that the runtime call can still replace.

Either way the contract is in the config comments: the calloc must zero the buffer, `NULL` must be accepted by free, and a non-null pointer to free must have come from the matching calloc.

**What the library does with the facility**

The library never calls `malloc` or `calloc` directly. Its allocation sites use the `mbedtls_calloc` / `mbedtls_free` names. Examples from the index include `mbedtls_pem_write_buffer`, `mbedtls_mpi_grow`, the PSA key-slot code, and the cipher context constructors in `cipher_wrap.c`. So a project's allocator sees every heap use inside the library.

The library also ships its own allocator, `MBEDTLS_MEMORY_BUFFER_ALLOC_C`, which uses a caller-supplied buffer. Its init function, `mbedtls_memory_buffer_alloc_init` (`library/memory_buffer_alloc.c:566-600`), zeroes a static heap, then calls `mbedtls_platform_set_calloc_free` with its own functions. It uses `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` when `MBEDTLS_THREADING_C` is on, and the unlocked pair otherwise. So the library uses the same hook to install its own allocator, and the project can do the same with a custom one. The buffer allocator's heap is a single static, so it supports one heap per process. Its `selftest` calls it in `programs/test/selftest.c`.

Limits worth knowing:
- The runtime hook is global, so it is one allocator per process, not per context.
- Only `calloc` and `free` are replaceable. There is no separate realloc hook.
- If the project's allocator fails, the library sees NULL and returns an error. It does not retry.

I read the core of this from the source and the config header. I did not check the buffer allocator's internal `buffer_alloc_calloc` functions, and I did not build anything to confirm the behaviour at run time.