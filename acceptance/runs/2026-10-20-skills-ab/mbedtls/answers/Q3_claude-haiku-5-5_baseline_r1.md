**Short answer:** library code never calls `calloc` or `free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, which are macros that resolve to either the system functions or a function-pointer dispatcher. The dispatcher is `library/platform.c`, and the library itself uses the same facility to install its own heap, `memory_buffer_alloc.c`.

**What gets called, by configuration**

| Build | `mbedtls_calloc` resolves to | Source |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | `calloc` directly, via macro | `include/mbedtls/platform.h:166-167` |
| `MBEDTLS_PLATFORM_MEMORY` on, both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `FREE_MACRO` defined | Your macro, at compile time | `platform.h:143-144` |
| `MBEDTLS_PLATFORM_MEMORY` on, no macros | `mbedtls_calloc()` in `platform.c`, which calls through a static function pointer | `platform.c:44-55` |

The third row is the runtime case. The pointers start as `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. Those default to `calloc` and `free`, unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set. Under that flag they become `platform_calloc_uninit`, which returns NULL, and `platform_free_uninit`, which does nothing (`platform.c:24-42`). Note that `MBEDTLS_PLATFORM_STD_CALLOC` is a config define, so the library's own variable declarations are also fixed by the time `platform.c` compiles.

**How a project substitutes its allocator**

Two routes, chosen at build time:

1. **Compile-time.** Define `MBEDTLS_PLATFORM_MEMORY` and both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (in `mbedtls_config.h` or via the compiler). `check_config.h:558-573` requires that the two macros be defined together. The macros are then used everywhere, and `platform.c` is left out of the build of that dispatcher.
2. **Runtime.** Define `MBEDTLS_PLATFORM_MEMORY` without the macros, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other library call. The function (`platform.c:57-63`) just stores the two pointers and returns 0. It does no validation, and it does not lock. The header says the call is not thread-safe, so do it at startup.

The config documentation (`mbedtls_config.h:154-208`) lists the same rules. `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_STD_CALLOC` cannot both be set.

**What the library does with the facility**

- **Its allocation sites.** Across `library/`, roughly 170 call sites use `mbedtls_calloc(`, spread over about 48 files, mainly `ssl_tls.c`, `psa_crypto.c`, `x509.c` and `pk_wrap.c`. A search for raw `calloc`/`malloc`/`free` outside `platform.c` and `memory_buffer_alloc.c` finds only comments.
- **Its own heap.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566`) carves a caller-supplied buffer into a managed heap. It then installs its own functions through `mbedtls_platform_set_calloc_free()`: `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed` when `MBEDTLS_THREADING_C` is on, and the unlocked pair otherwise (`memory_buffer_alloc.c:570-576`). So the buffer allocator is itself one of the substitutes that the runtime hook can install.
- **Consequence to watch for.** That install is global and unconditional. If an application sets its own allocator and then calls `mbedtls_memory_buffer_alloc_init`, the application's allocator is silently replaced. The call order matters.
- **Misuse checks.** The buffer allocator reports a free of a pointer it does not manage, or a free of an unallocated block, with a `FATAL` message to stderr (`memory_buffer_alloc.c:373, 390`).

**What I did not check:** the body of the mutex wrappers beyond their call sites, and whether `mbedtls_memory_buffer_alloc_free` restores the previous allocator. If that matters, read `memory_buffer_alloc.c` around its free function before relying on it.