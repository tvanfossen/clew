**What it accomplishes.** `MBEDTLS_PRIVATE(member)` is a compile-time guard on struct members declared in public headers. In `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

By default a member such as `ssl->state` is declared as `private_state`. Application code that writes `ssl->state` fails to compile, and the same code written as `ssl->MBEDTLS_PRIVATE(state)` still resolves. The layout is unchanged, so this is not an ABI change. The point is that the maintainers can rename, reorder or remove internal fields in a later release without silently breaking callers who reached into them. The `ssl.h` note at line 5163 says exactly this: direct access "could be broken in any future release." The guard turns that into a build error the caller sees, rather than a runtime surprise.

It is a guard, not access control. Anyone can write `MBEDTLS_PRIVATE(x)` by hand, or define `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the header.

**Who it is for.** Mostly it is for application authors, who get the rename and are the people it is meant to stop. Library code and a few programs need the real names, so they opt out.

**Where the opt-out is turned on in this tree (four places):**

| Location | Scope | Effect |
|---|---|---|
| `library/common.h:132` | Included by 129 of the library's `.c` files, plus `library/ssl_misc.h` (and so `ssl_debug_helpers_generated.c`, which includes it transitively) | Every library translation unit sees real member names. `common.h` is internal and not installed under `include/`, so this does not leak to applications. |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` sample program | Direct access such as `ssl->state` (about 27 `ssl->`/`conf->`/`ctx->` uses) compiles. |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` sample program | Same, though it uses far fewer members. |

Two things matter about how the opt-out is applied:

- **It must come before the public header.** The macro is expanded when `ssl.h` is parsed, and include guards stop a second parse. `ssl_server2.c` defines it on line 8, before `ssl_test_lib.h`. In the library, `common.h` is the first project include (for example `ssl_tls.c` line 12, before `mbedtls/ssl.h`). If a file included the public header first, the struct would already carry `private_` names and the define would have no effect.
- **For library code, the opt-out is global.** The 5 library files that write `MBEDTLS_PRIVATE(...)` explicitly (`ecdh.c`, `md.c`, `x509_crt.c`, `pk_internal.h`, `ssl_ciphersuites_internal.h`) are a leftover from before `common.h` was pulled in everywhere. Inside `common.h`'s scope, the explicit wrapper is redundant.

**Tests and other programs do not opt out.** `tests/suites/*.function` (for example `test_suite_x509write`, `test_suite_psa_crypto`) and `programs/ssl/ssl_context_info.c` and `programs/fuzz/fuzz_dtlsserver.c` reach private members by writing `MBEDTLS_PRIVATE(...)` at each access site. That is the per-expression form of the same escape hatch, and it is visible in the code, so anyone reading it can see the access is deliberate. `ssl.h` has 209 `MBEDTLS_PRIVATE(` occurrences, which is the public API surface the guard covers.

**What it means for the code in those places.** The library and the two `ssl_*2` samples are coupled to the internal field layout by design. Renaming a field inside the library is a normal refactor, but renaming a field used by `ssl_server2.c` or `ssl_client2.c` means touching those programs too. Anywhere else, direct member access fails to compile, and the fix is either a public accessor or an explicit `MBEDTLS_PRIVATE(...)`, which is the signal that the code depends on internals.