**What it does:** `MBEDTLS_PRIVATE(member)` is a rename, not an access check. `include/mbedtls/private_access.h:14-18` expands it to `private_##member` by default, so a struct field is really named `private_flags` (for example, `include/mbedtls/ssl_ciphersuites.h:455`). Code that writes `s.flags` then fails to compile, and code that writes `s.MBEDTLS_PRIVATE(flags)` compiles in both modes. The goal is to stop users depending on struct layout. The library can then add, reorder or retype fields in minor releases without breaking callers. The 3.0 migration guide says this directly (`docs/3.0-migration-guide.md:62-74`), and it calls `bar.MBEDTLS_PRIVATE(foo)` a last resort done "at your own risk."

It is not real access control. Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before the first mbedtls include turns the rename off for that translation unit. `ssl.h:5159-5169` marks that route as deprecated.

**Who gets the opt-out in this tree:**

| Where | Opted out? | Effect |
|---|---|---|
| `library/common.h:132` | Yes, unconditionally | Any library `.c` that includes `common.h` sees real field names. That is 107 of 109 files. Example: `library/ecdh.c:150` uses `ctx->MBEDTLS_PRIVATE(grp)`, which becomes `ctx->grp`. |
| `programs/ssl/ssl_server2.c:8`, `ssl_client2.c:8` | Yes, first line before any include | Sample programs get direct access to private fields across the whole file. |
| `programs/ssl/ssl_context_info.c:553-568` | No | It spells `MBEDTLS_PRIVATE(flags)` and similar, which compiles either way. I checked with `gcc -fsyntax-only` with and without the define; both exit 0. Without the define, the name expands to `private_flags`, which matches the struct. |
| Test suites (`test_suite_x509write.function:763`, `test_suite_psa_crypto.function:1329`) | No | Same macro spelling as `ssl_context_info.c`, so they work in both modes. |
| Application code | No (default) | Direct access fails to compile. Macro-spelled access works, but it is unsupported across minor versions. |

So the opt-out is for the library and its own sample programs. `ssl_context_info.c` is the one shipped program that reaches into private fields without opting out. It does that through the macro spelling, which is why it compiles either way.

**Caveat on ordering:** the opt-out only works if it is defined before `private_access.h` is first included. `library/ecdh.c` includes `common.h` on line 15, before any public header, so it works. A file that included a public header first would silently keep the renamed names and fail to compile.

I verified the expansions and the opt-out locations by reading the code and running syntax-only compiles. I did not run a full build or the test suite.