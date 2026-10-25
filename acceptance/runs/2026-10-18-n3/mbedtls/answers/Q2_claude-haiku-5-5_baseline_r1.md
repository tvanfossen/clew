**What it does.** `MBEDTLS_PRIVATE(member)` is a macro defined in `include/mbedtls/private_access.h:14-18`. By default it expands to `private_##member`, so `ctx->MBEDTLS_PRIVATE(state)` becomes `ctx->private_state`. That name doesn't exist, so code outside the library fails to compile when it touches a non-public field. The public structs in `include/mbedtls/*.h` (e.g. `ssl.h`) keep their layouts hidden, and the library can rename or reorder those fields without breaking callers who only used the documented API. The 3.0 migration guide (`docs/3.0-migration-guide.md:66-72`) describes this as the intended contract: documented public fields are stable, everything else should go through accessor functions.

**For whom.** The primary audience is application developers who link against Mbed TLS. They get a compile error instead of a silent dependency on internals. The library's own code is the exception, and it is the only thing that opts out.

**Where the opt-out is turned on in this tree:**

| Location | Effect |
|---|---|
| `library/common.h:132` | `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`, unconditionally. About 148 files include `common.h`, nearly all in `library/`. Every library translation unit therefore sees real member names, and `MBEDTLS_PRIVATE(x)` becomes plain `x`. |
| `programs/ssl/ssl_server2.c:8` | Defined before any include, so the sample server gets direct field access. |
| `programs/ssl/ssl_client2.c:8` | Same for the sample client. |

Nothing else in the repo defines the macro. Those are the only three places.

**What this means for the code in those places:**
- In `library/`, `MBEDTLS_PRIVATE(...)` is a no-op. Files such as `ecdh.c`, `md.c`, `x509_crt.c`, `pk_internal.h` and `ssl_ciphersuites_internal.h` use it, but it changes nothing in those builds. The wrapper only matters for consumers.
- The two sample SSL programs can read and write internal state. `ssl_server2.c` and `ssl_client2.c` are test and demo tools, so this is deliberate. The `ssl.h:5159-5169` warning says direct state access is deprecated and may break in any release.
- The order of includes matters. `private_access.h` has an include guard, so the macro is evaluated the first time that header is included. If a file pulled it in before `common.h` defined the opt-out, it would get `private_*` names. The existing build evidently gets the order right, since `ecdh.c` and the others compile.

**Anomaly I did not resolve.** `programs/ssl/ssl_context_info.c:553-568` uses `ciphersuite_info->MBEDTLS_PRIVATE(flags)`, `(cipher)` and `(mac)` but has no opt-out define, and it does not include the library-internal header. On the face of it that should resolve to `private_flags` and fail to compile. I did not build it to check. Running the program's build target (`programs/Makefile:325` or the CMake target `ssl_context_info`) would settle whether it is actually compiled in this configuration or whether the struct is visible some other way.