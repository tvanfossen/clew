**What it accomplishes.** `MBEDTLS_PRIVATE(member)` is a token-pasting macro, defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

By default, a struct member declared as `MBEDTLS_PRIVATE(state)` is actually named `private_state`. Code that writes `ssl->MBEDTLS_PRIVATE(state)` gets `ssl->private_state`, and code that writes `ssl->state` fails to compile. The macro does not add any access control. It makes the member name change, so that a user who reaches into a struct gets a compile error instead of silently depending on a layout that can change between releases. Mbed TLS' public headers, such as `ssl.h`, include this header, and `ssl.h:5159-5169` documents that direct access to `ssl->state` is deprecated and "could be broken in any future release."

**For whom.** The macro serves application developers, who are the users of the public API. The library's own code is the exception, and it opts out.

**Where the opt-out is turned on.** Three kinds of place define `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

1. **Library sources, globally.** `library/common.h:132` defines it unconditionally. About 130 files under `library/` include `common.h`, which means that the whole library compiles with the members un-prefixed. `common.h` only includes `mbedtls/build_info.h` and `alignment.h` before that line, so the define comes before any public struct header is read. The public headers therefore see `member`, not `private_member`. The library's own code can use `ctx->state` directly, and the names it uses match the real struct fields.

2. **Test and sample programs.** `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` define it at the top of the file, before including `ssl_test_lib.h`. These two programs opt out for their whole translation unit.

**What that means for code in those places.** Inside `library/` (and in those two programs), `MBEDTLS_PRIVATE(x)` expands to plain `x`. Code there can read and write any struct member, and a change to a field name breaks the library's own build. The protection only applies to external code, such as an application that includes `mbedtls/ssl.h` without defining the macro. For the library, the opt-out is the normal state, and the `MBEDTLS_PRIVATE` annotations in `library/` (for example in `ecdh.c`, `pk_internal.h`, `md.c`, `x509_crt.c` and `ssl_ciphersuites_internal.h`) have no effect when compiled there.

**Caveat on the claim about `common.h`.** I checked the define's position in `common.h` and the 130 includes of it. I did not open every library `.c` file to confirm that `common.h` is the first Mbed TLS header each one includes. If one of them included a public header before `common.h`, that file would see the `private_` names and would fail to compile against its own struct accesses, so the build would reveal it.