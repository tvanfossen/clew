**What it does.** `MBEDTLS_PRIVATE` is a macro in `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Each struct field in the public headers is declared as `MBEDTLS_PRIVATE(name)`, so by default the field is really called `private_name`. Code that writes `ssl->state` then fails to compile, and the only supported way in is the accessor functions (`mbedtls_ssl_is_handshake_over()`, `mbedtls_ssl_get_hostname()`, and so on). The layout and field names can change between releases without breaking callers, because nobody outside the library is meant to depend on them. The header is used in roughly 74 files, mostly `include/mbedtls/*.h` and `include/psa/*.h` (`ssl.h` alone has 210 uses).

**For whom.** The default protects the library's API boundary, meaning application developers who include the public headers. The opt-out is for code that is part of the library or the test tooling.

**Where the opt-out is turned on in this tree:**

| Location | Effect |
|---|---|
| `library/common.h:132` — `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Unconditional for all library translation units. `common.h` is included by `ssl_misc.h`, `ssl_ciphersuites.c`, `md.c`, `ecdh.c`, `x509_crt.c`, `pk.c` and `ssl_tls.c`, so inside the library `MBEDTLS_PRIVATE(x)` expands to plain `x`. |
| `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` | Defined before the first include, so these sample/test programs read `ssl->state`-style fields directly. |

What this means for the code in those places:

- **Library code.** The `MBEDTLS_PRIVATE(...)` spellings in `library/ecdh.c`, `library/md.c`, `library/x509_crt.c`, `library/pk_internal.h` and `library/ssl_ciphersuites_internal.h` are effectively documentation. They compile to the same thing as the bare field names. The library is compiled against the real field names everywhere, so the rename is invisible to it. Two consequences follow. First, the opt-out is not optional for the library: if a translation unit used a header that contained `MBEDTLS_PRIVATE` before `common.h` was included, it would expand to `private_x` and fail to build. Second, the macro gives no protection between library modules, which is intended.
- **Test and sample programs.** The two `ssl_*2.c` programs bypass the boundary on purpose, and they are the only in-tree consumers that do so. `programs/ssl/ssl_context_info.c` uses `MBEDTLS_PRIVATE(...)` without defining the opt-out, so it goes through the mangled names, which are the same as the real names only because the struct declarations use the same macro. Those programs are the ones that break if the struct layout changes.
- **External users.** Nothing in the public API turns the opt-out on. An application that defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including mbedtls headers gets direct access, but `ssl.h:5159–5169` marks that as deprecated and possibly broken in future releases.

**Limits of this check.** I did not build the tree or compile a test, so the claims about expansion and build failures come from reading the macro and the include graph, not from a compile. The include claims are from grepping `#include` lines in `library/`, not from following every transitive include. I also did not check the build system for any extra opt-out define (for example in CMake or `tests/`), so if one exists outside `.c`/`.h` sources it would not show up here.