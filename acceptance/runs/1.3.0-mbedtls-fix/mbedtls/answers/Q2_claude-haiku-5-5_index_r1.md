**What it does.** `MBEDTLS_PRIVATE(member)` is a rename, defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Public structs are declared with the wrapper, so `mbedtls_ssl_context` has `int MBEDTLS_PRIVATE(state);` (`include/mbedtls/ssl.h:1737`). By default that field is named `private_state`. Application code that writes `ssl->state` fails to compile, and `ssl->private_state` is not a documented access path either. The purpose is to make "this is not API" enforceable, so Mbed TLS can reorder, rename or remove members in minor releases without breaking callers that were only compiling by accident. It changes identifier spelling only, not layout, so it is not an ABI mechanism. The header's own warning (`ssl.h:5159-5169`) says direct access is deprecated and "could be broken in any future release".

**Who it is for.**

1. **External application code (the default).** Members are unnameable, so callers must use the accessors, such as `mbedtls_ssl_get_version_number()` and `mbedtls_ssl_session_get_id()`. The migration guide (`docs/3.0-migration-guide.md:68-74`) says the escape hatch `bar.MBEDTLS_PRIVATE(foo)` is "at your own risk".

2. **The library itself.** The opt-out is switched on in `library/common.h:132`:
   ```c
   #define MBEDTLS_ALLOW_PRIVATE_ACCESS
   ```
   About 107 library `.c` files include `common.h` directly, most as their first include. Inside them the macro expands to the plain name, so `ssl->state` compiles. That is why most library code has no `MBEDTLS_PRIVATE` at all. Only 14 occurrences remain in `library/`, mostly in internal headers such as `ssl_ciphersuites_internal.h` (8). I did not check the handful of `.c` files that do not include `common.h`.

3. **Test programs.** `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` define the opt-out before any include. Their whole translation unit can touch struct internals directly. `programs/fuzz/fuzz_dtlsserver.c` and `programs/ssl/ssl_context_info.c` do not define it, so they use the explicit `MBEDTLS_PRIVATE(...)` spelling, which still works because the struct and the access in that translation unit agree.

**What it means for the code in those places.**

- In `common.h`-first library files and the two ssl test clients, `MBEDTLS_PRIVATE(x)` is just `x`. Internals can be read and written, and a future change to that field has to be checked against them.
- The opt-out is per translation unit and must come before the first public header. The struct definition expands the macro when `ssl.h` is parsed. If a file includes `ssl.h` first and defines the opt-out afterwards, the struct has `private_state` while later code uses `state`, and the build fails. This is my reading of the macro, not something I built.
- Inline accessors in public headers, such as `mbedtls_ssl_is_handshake_over()` (`ssl.h:5148`), use `MBEDTLS_PRIVATE` too. They expand consistently in the consumer's translation unit, so they work for external callers.

I did not build the tree or run anything; these are read-only findings from the index and source.