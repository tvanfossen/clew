**What it does.** `MBEDTLS_PRIVATE(member)` is a token-pasting macro in `include/mbedtls/private_access.h`. By default it expands `ctx->MBEDTLS_PRIVATE(state)` to `ctx->private_state`, so the member is renamed. Code that writes `ssl->state` against the public header fails to compile. The renaming is the whole mechanism: the struct layout is unchanged, but the name a caller can type is no longer the real one.

**What it accomplishes.** It turns "members are private" from a comment into a compile-time error for outside code. Mbed TLS structs are defined in public headers, so without this, any application could reach into `mbedtls_ssl_context` and depend on fields the project reserves the right to reshuffle or rename between releases. The `ssl.h` doc comment says this directly: direct access to `ssl->state` is "deprecated and could be broken in any future release" (`include/mbedtls/ssl.h:5159-5169`).

**For whom.** Mainly external consumers, who get the renamed names by default. Internal code is the exception, and the exception is turned on by a single define:

- `library/common.h:132` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally. Library translation units that include `common.h` get `MBEDTLS_PRIVATE(x)` expanding to plain `x`. I checked this in `library/ssl_tls12_server.c`, which includes `common.h` at line 8 before any Mbed TLS header.
- `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` define it themselves, before including `ssl_test_lib.h`. These are test and sample programs, not library code, and they reach into context internals directly.

**What that means for those places.**

- Inside the library, the wrapper is a no-op. Code like `info->MBEDTLS_PRIVATE(key_exchange)` in `library/ssl_ciphersuites_internal.h` or `ctx->MBEDTLS_PRIVATE(md_info)` in `library/md.c:915` compiles to the plain field access. The internal code is coupled to struct layout, and a rename breaks it at compile time, not silently.
- The ordering is load-bearing. The macro is only the no-op if `common.h` (or the define) comes first in the translation unit. A library header that uses `MBEDTLS_PRIVATE(x)` and is included from a TU that skipped `common.h` would expand to `private_x` and fail to build. I checked the TUs I read, not every one of the library's 129 files that include `common.h`.
- In the two sample programs, the define means `ssl_server2.c` and `ssl_client2.c` see the true names everywhere in the file. Those programs are tied to the internal layout of the version they ship with, and nothing in the build flags them when the layout changes.

**Net.** The wrapper is the public-API boundary for applications. The library and its sample/test programs are the intended "for whom" of the opt-out, and it is a file-level define, not a per-field permission. Application code that defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` has opted out of the stability promise, which the header comments say is not guaranteed.