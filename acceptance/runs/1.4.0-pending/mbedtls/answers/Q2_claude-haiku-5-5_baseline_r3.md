**What it does.** `include/mbedtls/private_access.h` defines the macro:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Public structs (for example `mbedtls_ssl_context` in `include/mbedtls/ssl.h`) wrap their fields in `MBEDTLS_PRIVATE(...)`. By default each field is really named `private_state`, `private_flags`, and so on. Code that writes `ssl->state` against the public header fails to compile, so the field is effectively private. Mbed TLS can rename or reorder these fields without it counting as an API break. The `ssl.h:5163` doc comment says direct access is deprecated and "could be broken in any future release."

**For whom.** The mangling is aimed at external consumers. The library itself is the one party that is exempt.

**Where the opt-out is turned on in this tree:**

| Location | Scope | Effect |
|---|---|---|
| `library/common.h:132` | Every library TU that includes `common.h` (nearly all of `library/*.c`) | Members use their real names. Library code writes `ctx->state` directly. |
| `programs/ssl/ssl_server2.c:8` | That one test driver | Defined before `ssl_test_lib.h` includes `ssl.h`, so the whole TU sees real names. |
| `programs/ssl/ssl_client2.c:8` | That one test driver | Same as above. |

Nothing in `tests/suites/` or the fuzz/context-info programs defines the macro. They use `MBEDTLS_PRIVATE(x)` explicitly on the few fields they need, e.g. `programs/ssl/ssl_context_info.c:553` and `programs/fuzz/fuzz_dtlsserver.c:138`. That spelling works without a global opt-out because the header uses the same mangling, so both sides agree.

**What the opt-out means for the code in those places.** Library and driver code couples directly to the struct layout and field names. A rename inside the library is a compile-time change for those files, but it is internal and invisible to users. Consumers who define `MBEDTLS_ALLOW_PRIVATE_ACCESS` themselves get the same access with no compatibility promise.

**Ordering is load-bearing.** The `#ifndef` is evaluated the first time `private_access.h` is included, not at each use. `mbedtls/platform.h:28` includes it, and most public headers include `platform.h`. So `common.h` has to define the macro before any public header is reached. I checked this:
- `common.h` pulls in only `build_info.h` and `alignment.h`, and the config chain does not reach `platform.h`. That ordering holds.
- `library/x509_internal.h:12` includes `private_access.h` directly. Every file that includes it (`x509*.c`, `pkcs7.c`) includes `common.h` first.
- `ssl_misc.h` includes `common.h` before `mbedtls/ssl.h`.
- `pk_internal.h` and `ssl_ciphersuites_internal.h` include public headers without `common.h`. They are safe only because their includers (`pk*.c`, `x509_crt.c`) include `common.h` first. I did not check the `ssl_ciphersuites_internal.h` includers.

If a library file pulled a public header in before `common.h`, its member accesses would silently expand to `private_*` names and fail to compile. The tree relies on include order for this, not on any enforced check.

I did not use the `dossier` tool mentioned in a hook message; it is not among my available tools, and the grep and read results above were enough to answer.