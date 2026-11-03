**What it does:** `MBEDTLS_PRIVATE(member)` is a macro that renames a struct field so that ordinary code can't reach it by name. In `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

So `ctx->MBEDTLS_PRIVATE(state)` compiles to `ctx->private_state` by default. A user who writes `ctx->state` gets a compile error, and the public header never promises that field exists. That is the point: the library can rename, reorder or retype internals in a minor release without breaking callers, and it keeps the public ABI/API surface small. The `ssl.h` doc comment on `mbedtls_ssl_handshake_step` says this directly: direct access to `ssl->state` is "deprecated and could be broken in any future release."

**For whom:** the macro serves *library consumers*. The library itself is the other party, and it needs the real names. The mechanism is a single define, `MBEDTLS_ALLOW_PRIVATE_ACCESS`, which turns the macro into the identity. Where it is turned on in this tree:

| Location | Effect |
|---|---|
| `library/common.h:132` | Defined for every library translation unit that includes `common.h` before the public headers. Library code in e.g. `ssl_tls.c`, `ecdh.c`, `md.c` can write `ssl->state` or `info->key_exchange` directly, and the `MBEDTLS_PRIVATE(...)` wrappers in `library/pk_internal.h`, `library/ssl_ciphersuites_internal.h` and `library/md.c` resolve to the plain names too. |
| `programs/ssl/ssl_server2.c:8` | Defined in the test server program. |
| `programs/ssl/ssl_client2.c:8` | Defined in the test client program. |

Consequences:

- **Inside the library**, the wrappers are cosmetic. The `common.h` define means every internal file sees plain field names, and the ordering matters: `common.h` must come before `mbedtls/*.h`, which `ecdh.c` and `ssl_tls.c` respect.
- **Test and tool code** that is not one of those translation units gets the mangled names. `tests/suites/*.function` uses `MBEDTLS_PRIVATE(...)` (e.g. `test_suite_x509write.function:763`, `test_suite_psa_crypto.function:1329`), and the test suites don't define the opt-out. Tests therefore exercise the same access rules as external users, which is the stated intent.
- **The two `programs/ssl` files** define the opt-out but, in this tree, I found no `->state`/`MBEDTLS_PRIVATE` access in them, nor in `ssl_test_lib.[ch]`. The define may be vestigial. I didn't verify that by compiling, so treat it as "appears unused."
- **Documented escape hatch:** `docs/3.0-migration-guide.md:74` tells users they can write `bar.MBEDTLS_PRIVATE(foo)` or define the opt-out themselves, "at your own risk." The define is a per-translation-unit switch, so defining it in a consumer's `.c` file before including Mbed TLS headers gives that consumer full access. The Doxygen config (`doxygen/mbedtls.doxyfile:25`) expands `MBEDTLS_PRIVATE` so the docs stay readable.

Net: the wrapper protects external callers from depending on internals. Library code is exempt through `common.h`, and anyone who needs internals anyway has to opt out explicitly and accept that breakage is possible.