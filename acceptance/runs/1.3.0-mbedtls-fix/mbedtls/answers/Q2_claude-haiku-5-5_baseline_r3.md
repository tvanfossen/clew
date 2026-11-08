**What it does.** `MBEDTLS_PRIVATE(x)` is defined in `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Every public struct field is spelled this way in the headers (889 occurrences across 74 files). Without the opt-out, `ctx->MBEDTLS_PRIVATE(state)` becomes `ctx->private_state`, so the real name `state` no longer exists. Plain `ctx->state` then fails to compile. The point is to keep struct layout out of the stable API. `docs/3.0-migration-guide.md:64-68` says minor releases may add, remove, reorder or retype fields. Renaming turns a silent breakage into a compile error.

It is not a security boundary. The rename exists only at compile time, and the fields still exist in the binary.

**Who gets the opt-out.** The only place it is defined in the library is `library/common.h:132`. Everything else that defines it is in the tree's own programs:

| Where | Effect |
|---|---|
| `library/common.h:132` | Library sources that include `common.h` see the real field names. In this tree 107 of the 109 `library/*.c` files include it, so the library code is the main beneficiary. |
| `programs/ssl/ssl_server2.c:8`, `programs/ssl/ssl_client2.c:8` | Each defines the macro before `ssl_test_lib.h`, so they read and write fields directly. These are test/demo programs, not shipped API. |

Everything else uses the `MBEDTLS_PRIVATE(...)` spelling without the opt-out. That spelling works in both modes because the header side and the user side are renamed the same way. For example, `tests/suites/test_suite_x509write.function:763` writes `ctx.MBEDTLS_PRIVATE(extensions)`, which compiles without the define. I checked this with `gcc -fsyntax-only`.

`include/mbedtls/ssl.h:5163` says that reaching handshake state through `ssl->MBEDTLS_PRIVATE(state)` or by defining the opt-out is deprecated and may break in any release. The migration guide (line 74) says the same thing about `bar.MBEDTLS_PRIVATE(foo)`.

**Ordering hazard.** The `#ifndef` in `private_access.h` is evaluated once, at the first inclusion in each translation unit. The opt-out only works if `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined before any mbedtls header is included. I confirmed this with three small compiles against `mbedtls/x509_crt.h`:

- Define before include, plain `c->extensions`: compiles.
- No define, plain `c->extensions`: error.
- Define after include, plain `c->extensions`: error. The define comes too late.

This is why `common.h` is the first include in the library `.c` files that need it (for example `library/ssl_tls.c:12`, `library/md.c:12`, `library/x509_crt.c:20`). A consumer that defines the macro after including an mbedtls header gets the mangled names with no warning.

**Practical reading for this tree.** The opt-out is for the library itself and two test/demo programs. Those places are free to depend on real field names, so they must be rebuilt together with the headers. Application code in this repo should use the `MBEDTLS_PRIVATE(...)` spelling or the public accessors, not the opt-out.