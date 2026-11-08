**Short answer:** by default, `mbedtls_calloc` and `mbedtls_free` are macros that expand to libc `calloc` and `free`. Every allocation inside the library goes through those two names. A project can replace them at compile time with two macros, or at runtime with one setter function. The library's own use of the facility is mostly as a hook point for its optional built-in arena allocator.

**What gets called**

- Without `MBEDTLS_PLATFORM_MEMORY`, `include/mbedtls/platform.h` (around line 164) does `#define mbedtls_calloc calloc` and `#define mbedtls_free free`.
- Library code calls `mbedtls_calloc(n, size)` and `mbedtls_free(p)`, about 169 call sites across roughly 48 `library/*.c` files. A direct grep finds no raw `malloc` or `calloc` calls elsewhere in `library/`.

**Substitution, option 1: compile time**

Define `MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in `mbedtls_config.h` or the compiler flags. `platform.h` then points `mbedtls_calloc` and `mbedtls_free` straight at your functions. The check in `include/mbedtls/check_config.h` requires the two macros to be defined together, and does not allow `MBEDTLS_PLATFORM_STD_CALLOC` alongside them.

**Substitution, option 2: runtime**

Define only `MBEDTLS_PLATFORM_MEMORY`. Then `mbedtls_calloc` and `mbedtls_free` become real functions in `library/platform.c`, which forward through two function pointers. Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before the library allocates anything. The default for those pointers is `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`:

- If the project defines those two macros, they are used.
- If `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set and nothing is defined, the defaults are stubs. `calloc` returns NULL and `free` does nothing, so the library fails cleanly until a setter runs.
- Otherwise the defaults are libc `calloc` and `free`.

**What the library does with the facility**

- `library/memory_buffer_alloc.c` (around line 572) is an optional built-in arena allocator, enabled by `MBEDTLS_MEMORY_BUFFER_ALLOC_C`. Its `mbedtls_memory_buffer_alloc_init()` calls `mbedtls_platform_set_calloc_free()` itself, installing its own calloc and free. It uses a mutexed wrapper when `MBEDTLS_THREADING_C` is on.
- Side effect: calling `mbedtls_memory_buffer_alloc_init()` silently replaces whatever allocator the project had installed. Only one of the two should be in charge.

**Caveats I did not verify in this tree**

- I did not find a documented thread-safety rule for `mbedtls_platform_set_calloc_free()`. It is an unguarded pointer write, so calling it before any thread starts is the safe pattern.
- I did not check whether the test suites exercise the runtime setter beyond the config-consistency entries in `tests/suites/test_suite_config.mbedtls_boolean.data`.