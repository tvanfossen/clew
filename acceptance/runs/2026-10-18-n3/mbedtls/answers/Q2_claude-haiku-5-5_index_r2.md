**What it does.** `MBEDTLS_PRIVATE(member)` is a preprocessor switch on every public struct member. In `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

By default the member is renamed to `private_<name>`. Application code that writes `ctx->state` then fails to compile, because no such member exists. Code that writes `ctx->MBEDTLS_PRIVATE(state)` also fails, and this is the mechanism that keeps internals out of the public API. The field layout is still visible in the header, so the rename is a compile-time guard against accidental use, not an access-control boundary. The `ssl.h` warning at lines 5159-5169 spells out the policy: direct access to `ssl->state` is "deprecated and could be broken in any future release."

**Who gets the opt-out.** The define `MBEDTLS_ALLOW_PRIVATE_ACCESS` is turned on in exactly three places in this tree:

1. **`library/common.h:132`**: the library's own internal header. Most `library/*.c` and `library/*.h` files include it (the grep matched 129 files under `library/`). For them, every `MBEDTLS_PRIVATE(x)` expands to plain `x`, so the library reads and writes its own struct internals directly. This is the main opt-out, and it covers the whole library build.
2. **`programs/ssl/ssl_client2.c:8`** and **`programs/ssl/ssl_server2.c:8`**: the test/sample TLS programs. They define it before any include, so they reach into SSL context internals such as the state machine. These programs are not a supported API surface, and the define is what lets them compile against the private layout.

**What this means for the code in those places.**

- Inside the library, the macro is effectively a no-op. The `MBEDTLS_PRIVATE` uses in `library/ecdh.c`, `library/ssl_ciphersuites_internal.h`, `library/md.c`, `library/x509_crt.c`, and `library/pk_internal.h` compile to the real member names.
- The define is evaluated when the preprocessor expands the struct declaration in the header, not when the field is used. So `MBEDTLS_ALLOW_PRIVATE_ACCESS` must be defined before the first include that pulls in a struct header. In the two `ssl_*2.c` programs it is (line 8, before `ssl_test_lib.h`). If some `.c` file included `mbedtls/ssl.h` before `common.h`, the struct would be declared with `private_state` while the code later refers to `state`, which fails to compile. The `common.h` path is the one the library relies on, so this ordering is a real constraint for new library files.
- In the two programs, reading `ssl->state` works, but it is fragile by the header's own account. Any upgrade can break it without notice.

**Limits of what I checked.** I did not read the 3.0 migration guide (`docs/3.0-migration-guide.md`) or the test `.function` files that use `MBEDTLS_PRIVATE`. I did not confirm whether the test suites define the opt-out through a path other than the three hits above. Those would be the next places to check if you need the complete picture.