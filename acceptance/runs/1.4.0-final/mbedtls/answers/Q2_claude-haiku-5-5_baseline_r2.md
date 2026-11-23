**What it does.** `MBEDTLS_PRIVATE(member)` is a macro in `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

By default a struct field is renamed to `private_<name>`. Code outside the library that writes `ctx->state` fails to compile, and code that writes `ctx->MBEDTLS_PRIVATE(state)` also fails, because the real name is `private_state`. The point is to keep the field layout and names free to change between releases. The struct headers in `ssl.h`, `rsa.h`, `cipher.h` and others are public, so without the wrapper any application that touched a field would break on a minor-version change.

**For whom.** Three audiences, depending on the define:

| Who | Define in effect? | Effect on their code |
|---|---|---|
| Applications linking libmbedtls (default) | No | Direct member access is a compile error. They must use the public API. |
| Library sources (`library/*.c`) | Yes, via `library/common.h:132` | Plain member names. `library/ssl_misc.h` includes `common.h` before `ssl.h`, so the define is in place when the structs are parsed. |
| In-tree programs `programs/ssl/ssl_server2.c:8` and `ssl_client2.c:8` | Yes, defined on line 8 before any include | The whole translation unit sees plain names, so these two programs are coupled to the internal layout. |

**What the opt-out means in practice.**

- The two `ssl_*2.c` programs are the only out-of-library code that opts out. They are test and example tools shipped in the same tree, so they move with the library. Application code should not copy this define. The header doc (`include/mbedtls/ssl.h` around line 5163) and the 3.0 migration guide (lines 62–74) both say defining it is deprecated and unsupported across releases, and the migration guide says "at your own risk".
- The define only affects translation units that see it before the struct header. A library file that includes a public header before `common.h` would get the mangled names and fail to build. I did not audit every `.c` file for include order. The two library files that do not include `common.h` (`ecp_curves_new.c`, `ssl_debug_helpers_generated.c`) would fail to compile if they touched struct members directly, so the build would catch that case.
- The test suites `tests/suites/test_suite_psa_crypto.function` and `test_suite_x509write.function` use `MBEDTLS_PRIVATE(...)` but do not define the opt-out. They are on the public side of the boundary.