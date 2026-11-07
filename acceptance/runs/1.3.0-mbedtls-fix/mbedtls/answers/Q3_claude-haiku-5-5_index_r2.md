## Short answer

Library code never calls `calloc`/`free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, and what those resolve to depends on configuration. With the default config they are plain libc `calloc`/`free`. A project substitutes its own allocator either at compile time (macros) or at runtime (a function-pointer setter).

## What gets called

```
library code (cipher_wrap.c, ecp.c, asn1parse.c, ...)
        │  mbedtls_calloc(n, sz) / mbedtls_free(p)
        ▼
library/platform.c:47,52     mbedtls_calloc / mbedtls_free      (only if MBEDTLS_PLATFORM_MEMORY)
        │  (*mbedtls_calloc_func)(n, sz)
        ▼                       platform.c:44-45 (static pointers)
  default = MBEDTLS_PLATFORM_STD_CALLOC / _FREE
  or set by mbedtls_platform_set_calloc_free()  (platform.c:57)
```

Three build modes, from `include/mbedtls/platform.h:138-168`:

| Config | `mbedtls_calloc` resolves to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default, `mbedtls_config.h:208` is commented out) | `calloc` via macro, no indirection |
| `MBEDTLS_PLATFORM_MEMORY` + both `_CALLOC_MACRO` and `_FREE_MACRO` | your macro, inlined at compile time |
| `MBEDTLS_PLATFORM_MEMORY` only | a function pointer, set at runtime |

## How a project substitutes its allocator

**Compile time.** Define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. You must define both macros or neither. `platform.h:139-144` aliases `mbedtls_calloc`/`mbedtls_free` to them, and `platform.c:20-22` drops its own pointer machinery entirely. The macro must zero the memory and `free` must accept `NULL`, per the `MBEDTLS_PLATFORM_STD_CALLOC` contract (`mbedtls_config.h:4113-4133`).

**Runtime.** Define only `MBEDTLS_PLATFORM_MEMORY`, then call early at startup:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

The default target without a set call is `MBEDTLS_PLATFORM_STD_CALLOC` if you define it, and otherwise a stub that returns `NULL` (`platform.c:24-33`). The stub `free` does nothing. So forgetting the setter does not crash. Every allocation quietly fails and the library reports out-of-memory errors.

## What the library does with the facility

- **Everything routes through it.** A grep of `library/` for raw `calloc(`/`free(` finds no real calls outside the hook. The one exception is `memory_buffer_alloc.c:404`, `free(hdr->trace)`, which looks like a backtrace-only path. I did not confirm its guard. The index resolves about 147 callers of `mbedtls_calloc` and 133 of `mbedtls_free`, across cipher, pk, ecp, asn1 and the test programs.
- **The library ships its own allocator on top of the hook.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566`) carves allocations out of a caller-supplied static buffer. It calls `mbedtls_platform_set_calloc_free()` to install `buffer_alloc_calloc_mutexed`/`_free_mutexed`, or the unmutexed pair if threading is off. Block headers carry `magic1`/`magic2` checks, and misuse is reported with `FATAL` messages (lines 373, 390).
- **Test design reinforces it.** `component_test_psa_crypto_without_heap` (`tests/scripts/components-configuration-crypto.sh`) builds a config where the core library, including PSA core, cannot call `calloc`/`free`, while test code can.

## Caveats

- The hooks are process-global, unsynchronized function pointers. I'd set them once at startup, before any threads start. That is an inference from the code, not something the docs state.
- `mbedtls_memory_buffer_alloc_init` returns early on a too-small buffer, after installing the hooks but before setting up the heap (`memory_buffer_alloc.c:580-582`). I did not trace what an allocation then does. Check that before relying on it in a constrained build.