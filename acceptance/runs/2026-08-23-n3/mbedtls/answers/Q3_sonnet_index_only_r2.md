## What actually gets called

Every allocation in the library goes through `mbedtls_calloc(nmemb, size)` — never a bare `calloc()`. The index shows `mbedtls_calloc` has well over 130 resolved callers spread across nearly every module: cipher/ECP/RSA/PK contexts, ASN.1/X.509 parsing, the TLS handshake state machine, PSA crypto, PEM read/write, and so on. There is no path in the library that reaches the heap directly.

`mbedtls_calloc` itself, however, is not fixed logic — it's one of two things depending on build configuration (`include/mbedtls/platform.h:139-167`, gated by `MBEDTLS_PLATFORM_MEMORY`):

- **Default (no `MBEDTLS_PLATFORM_MEMORY`)**: `mbedtls_calloc` is a plain macro expanding to `calloc` (and `mbedtls_free` to `free`) — libc's allocator, called directly, no indirection.
- **With `MBEDTLS_PLATFORM_MEMORY` defined** (declared in `MBEDTLS_PLATFORM_CALLOC_MACRO`/`MBEDTLS_PLATFORM_FREE_MACRO`, or falling through to the default): `mbedtls_calloc` becomes a real function in `library/platform.c:47-50` whose body is exactly:

```c
void *mbedtls_calloc(size_t nmemb, size_t size)
{
    return (*mbedtls_calloc_func)(nmemb, size);
}
```

It just dereferences a function pointer. `mbedtls_calloc_func` is a static variable in `platform.c:44`:

```c
static void *(*mbedtls_calloc_func)(size_t, size_t) = MBEDTLS_PLATFORM_STD_CALLOC;
```

— initialized to whatever `MBEDTLS_PLATFORM_STD_CALLOC` resolves to (ordinarily `calloc` again), but it's a mutable pointer, not a constant.

## How a project substitutes its own allocator

`library/platform.c:57-63` defines the swap point:

```c
int mbedtls_platform_set_calloc_free(void *(*calloc_func)(size_t, size_t),
                                     void (*free_func)(void *))
{
    mbedtls_calloc_func = calloc_func;
    mbedtls_free_func = free_func;
    return 0;
}
```

A project enables `MBEDTLS_PLATFORM_MEMORY` in `mbedtls_config.h`, then calls `mbedtls_platform_set_calloc_free()` once at startup with its own `calloc`/`free`-shaped functions (e.g. a pool allocator, a heap-tracking wrapper, or a stack-based allocator for a no-heap embedded target). From that point every one of the ~130+ call sites — unchanged — routes through the new functions, because they all called the indirection (`mbedtls_calloc`/`mbedtls_free`), never libc directly. This is the textbook use case the config gate `MBEDTLS_PLATFORM_MEMORY` exists for; the index shows it's actually exercised in only two places in-tree: `configs/ext/tfm_mbedcrypto_config_profile_medium.h` (Trusted Firmware-M profile) and `tests/configs/user-config-malloc-0-null.h` (a test config), which corroborates that this is meant to be turned on by an *integrator's* config, not the library's own default build.

## What the library itself does with the facility

The library ships one concrete consumer of this exact mechanism: `mbedtls_memory_buffer_alloc_init()` in `library/memory_buffer_alloc.c:566-600`. Its whole job is to call `mbedtls_platform_set_calloc_free()` itself, pointing the global function pointers at its own bump/free-list allocator that manages a single caller-supplied static buffer instead of touching the heap:

```c
#if defined(MBEDTLS_THREADING_C)
    mbedtls_mutex_init(&heap.mutex);
    mbedtls_platform_set_calloc_free(buffer_alloc_calloc_mutexed,
                                     buffer_alloc_free_mutexed);
#else
    mbedtls_platform_set_calloc_free(buffer_alloc_calloc, buffer_alloc_free);
#endif
```

So this is a self-hosted example of the same substitution mechanism it exposes to integrators: a stack/static-buffer allocator for heap-less targets, with an optional mutex-guarded variant when `MBEDTLS_THREADING_C` is on. Its own doc comment (surfaced by dossier) states the intent plainly: "does memory management inside the presented buffer and does not call calloc() and free()."

One gap the index can't close: it has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO`/`MBEDTLS_PLATFORM_FREE_MACRO` themselves — that's expected, since they're meant to be user-supplied overrides (or left undefined so the function-pointer path in `platform.c` is used), not something the shipped config headers define.
