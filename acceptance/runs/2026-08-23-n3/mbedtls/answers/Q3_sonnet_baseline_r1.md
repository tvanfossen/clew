I now have what I need to answer.

## What actually gets called

Every internal allocation in mbedtls goes through two library-wide symbols, `mbedtls_calloc()` and `mbedtls_free()` — there is no direct `malloc`/`free` scattered through the codebase (48 files in `library/` call `mbedtls_calloc()`, none call libc `calloc` directly). What those two symbols *resolve to* is decided entirely at compile time by `include/mbedtls/platform.h`:

- **Default (`MBEDTLS_PLATFORM_MEMORY` undefined):** `platform.h` `#define`s `mbedtls_calloc` → `calloc` and `mbedtls_free` → `free` as raw macros (`platform.h:166-167`). No indirection, no function pointers — the library links straight to libc.
- **`MBEDTLS_PLATFORM_MEMORY` enabled, with `MBEDTLS_PLATFORM_CALLOC_MACRO`/`FREE_MACRO` also defined:** `mbedtls_calloc`/`mbedtls_free` are macros expanding to whatever you named (compile-time substitution, `platform.h:143-144`).
- **`MBEDTLS_PLATFORM_MEMORY` enabled, without those macros:** `mbedtls_calloc`/`mbedtls_free` become real functions declared in `platform.h:148-149` and defined in `library/platform.c`. There, they're thin wrappers that indirect through file-scope function pointers `mbedtls_calloc_func`/`mbedtls_free_func` (`platform.c:44-55`), settable at *runtime* via `mbedtls_platform_set_calloc_free()`. If nothing has set them yet, they default to `MBEDTLS_PLATFORM_STD_CALLOC`/`FREE`, which itself defaults to libc `calloc`/`free` unless overridden, or — if `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set — to stub functions (`platform_calloc_uninit` always returns NULL, `platform_free_uninit` is a no-op) so an unconfigured allocator fails safe instead of silently calling into libc.

## How a project substitutes its own allocator

Two mechanisms, mutually exclusive, both gated by enabling `MBEDTLS_PLATFORM_MEMORY` in `mbedtls_config.h`:

1. **Compile-time (macro) substitution** — also define `MBEDTLS_PLATFORM_CALLOC_MACRO`/`MBEDTLS_PLATFORM_FREE_MACRO` to your function names. `mbedtls_calloc`/`mbedtls_free` become macros for your functions everywhere the library is built. No indirection cost, but fixed at build time — you can't swap allocators per instance or at runtime.
2. **Runtime substitution** — leave those macros undefined; call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` once during startup before using any mbedtls API. This just stores your function pointers into `mbedtls_calloc_func`/`mbedtls_free_func`; every subsequent `mbedtls_calloc()`/`mbedtls_free()` call in the library indirects through them. This is the mechanism embedded/RTOS ports typically use (e.g. to route through an RTOS heap or a pool allocator), and it's how the config doc's decision table (`mbedtls_config.h:172-201`) frames it.

The library also ships its own reference allocator for exactly this slot: `library/memory_buffer_alloc.c` / `include/mbedtls/memory_buffer_alloc.h`. `mbedtls_memory_buffer_alloc_init(buf, len)` hands it a fixed static buffer and it does bump/free-list management inside that buffer instead of touching the system heap at all — useful on targets with no heap, or where you want a hard cap on TLS's memory footprint and buffer-overflow/leak instrumentation (`MBEDTLS_MEMORY_VERIFY_*` flags). It self-installs by calling `mbedtls_platform_set_calloc_free()` with its own functions (per its own doc comment, `memory_buffer_alloc.h:45-46`), so it's implemented as a *consumer* of the same runtime substitution hook a project's own allocator would use — not a special-cased third path.

## What the library does with the facility

Nothing more clever than calling it. Every dynamic buffer inside mbedtls — ASN.1 parse trees, PK contexts, cipher/session state, X.509 chains, etc. — is obtained via `mbedtls_calloc()` and released via `mbedtls_free()` (see the doc cross-references in `asn1.h`, `oid.h`, `pk.c`, `cipher.c`). The library itself never assumes anything about what backs those calls beyond the contract (`calloc`-style zero-initialized alloc, `free`-style release, NULL-safe free). It doesn't retry, pool, or introspect allocations — all of that is left to whatever you plug into the two hooks above. The only place the library *supplies* allocator behavior itself is the optional `memory_buffer_alloc` module, which exists as a reference/default implementation for no-heap targets, not as special internal plumbing.
