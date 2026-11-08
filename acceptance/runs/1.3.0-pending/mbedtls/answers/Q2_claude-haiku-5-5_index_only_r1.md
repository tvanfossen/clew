**What it does:** `MBEDTLS_PRIVATE(member)` is a rename, not an access control. In `include/mbedtls/private_access.h:15` it expands to `private_##member` by default, so a struct field declared as `MBEDTLS_PRIVATE(nr)` is actually named `private_nr` in the compiled header. Code that writes `ctx->nr` against the public header fails to compile, and code that wants the field has to use the prefixed name. The index confirms the wrapping on the AES context (`mbedtls_aes_context`, `aes.h`), and the file's own documentation calls it a "Macro wrapper for struct's members."

**Why:** Public headers declare full struct layouts, so without the wrapper applications could depend on internal fields. The library's own doc comment (`library/common.h`, MBEDTLS_ALLOW_PRIVATE_ACCESS) says the intent: structs are publicly visible, but their members "are private and should not be accessed by the user." The rename turns accidental use into a compile error, which keeps the internal layout free to change. It is a guardrail against misuse, not a security boundary: anyone can define the opt-out macro or use the prefixed name.

**Who the opt-out is for:** The switch is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. `private_access.h:14-18` gates the two branches on it: if it is undefined, `MBEDTLS_PRIVATE(m)` becomes `private_##m`; if it is defined, it becomes plain `m`. The index finds three places that define it:

| Site | Who it covers | What it means there |
|---|---|---|
| `library/common.h:132` | The library's own sources (it's the internal "utility macros" header) | Library code reads and writes struct fields directly. Changing a private field means updating library code too. |
| `programs/ssl/ssl_client2.c:8` | The test/diagnostic client program | Can touch TLS internals, so it breaks if those fields are renamed or restructured. |
| `programs/ssl/ssl_server2.c:8` | The test/diagnostic server program | Same as the client. |

For application developers, nothing changes: they get the prefixed names and can't reach fields without defining the macro themselves. The users who are exempt are the library and its bundled test programs, which are coupled to internal layout by design.

**Caveats from the index:**
- The index doesn't show whether `library/common.h:132` sits inside a further conditional, only that it's a bare `#define`. The `#ifndef` in `private_access.h` is evaluated when that header is first included, so the define only takes effect if `common.h` comes before `private_access.h` in each translation unit. I didn't verify the include order.
- The index's `MBEDTLS_PRIVATE` "function" rows (e.g. `mbedtls_aes_context::MBEDTLS_PRIVATE(nr)`) are artifacts of doxygen recording each wrapped field as a function. Treat them as field declarations, not callable functions.
- The index's caller data for `MBEDTLS_PRIVATE` is ambiguous across 336 signatures, so I didn't attribute usages to specific struct members.