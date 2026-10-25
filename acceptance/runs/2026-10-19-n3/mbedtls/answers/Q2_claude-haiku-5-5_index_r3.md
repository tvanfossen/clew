**What it does.** `MBEDTLS_PRIVATE(member)` is a preprocessor macro in `include/mbedtls/private_access.h:14-18`. By default it expands to `private_##member`, so `ctx->MBEDTLS_PRIVATE(state)` becomes `ctx->private_state`. The member is renamed, not hidden, so code that names the field directly no longer compiles. That is the whole mechanism. Every public header that has struct members wraps them this way, and the header itself is pulled in by about 45 of them (for example `ssl.h:13`, `rsa.h:18`, `aes.h:30`).

**Who it is for.** It is aimed at application code. Its purpose is to keep users off the internal layout of structs so the library can change them without breaking callers. The `ssl.h` documentation says so directly. Near line 5162, the `mbedtls_ssl_handshake_step` warning says direct access to `ssl->state` is deprecated and "could be broken in any future release", and it points users to an API request instead.

**Where the opt-out is turned on.** Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before the header is included makes the macro expand to the plain member name (`private_access.h:16-17`). In this tree that define appears in only three places:

1. **`library/common.h:132`**, an unconditional `#define`. Library sources that include `common.h` get the plain names. Test suites that include `common.h` do too (for example `test_suite_common.function`, `test_suite_pkcs12.function`, `tests/src/certs.c`). `library/ssl_misc.h:14` also includes it, so the internal SSL code gets the access as well.
2. **`programs/ssl/ssl_server2.c:8`** and **`programs/ssl/ssl_client2.c:8`**, defined before any include. These sample programs read and write SSL internals directly.

**What that means in practice.**
- Library internals are not restricted. They can touch any field, and renaming a field there is a plain code change with no wrapper involved.
- The two SSL demo programs are the only application-level code in the tree that opts out. They depend on internal layout and would need updating if fields move. The `ssl.h` warning applies to them.
- Anyone who defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` in their own code gets the same access. Nothing enforces it except the rename, so an out-of-tree build that opts out is on its own when the layout changes.
- `test_suite_x509write.function:763` uses `ctx.MBEDTLS_PRIVATE(extensions)` and does not include `common.h` itself. I did not confirm how that file gets the define. It probably comes through the generated test harness, but I did not verify this.