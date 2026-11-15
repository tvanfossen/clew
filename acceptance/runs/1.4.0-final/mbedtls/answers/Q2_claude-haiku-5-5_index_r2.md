**What it does.** `MBEDTLS_PRIVATE(member)` is defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Each struct member in a public header is written as, for example, `int MBEDTLS_PRIVATE(nr);` (`include/mbedtls/aes.h:64`). By default the member is renamed to `private_nr`. Code that reaches into `ctx.nr` or `ctx->nr` then fails to compile, which tells the user the field is not part of the API. The field can also be renamed, reordered or removed without breaking anything that is documented as public. The header comment in `ssl.h:5163` says direct access is deprecated and could break in any release.

**For whom.** The default is for application developers who link against mbedTLS. They get the rename and cannot touch the internals by accident. The opt-out is for the library's own sources and its sample programs.

**Where the opt-out is turned on in this tree:**

| Location | What it does |
|---|---|
| `library/common.h:132` | Unconditionally `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`. Library `.c` files include `common.h` first (e.g. `ecdh.c:15`, `md.c:12`, `x509_crt.c:20`), so their struct accesses use the real member names. |
| `programs/ssl/ssl_server2.c:8` | Defined before `ssl_test_lib.h`, so this sample server reaches into SSL internals. |
| `programs/ssl/ssl_client2.c:8` | Same as the server. |

No other file in the tree defines it. The grep across the whole repo found only these four definition sites.

**What that means for the code in those places:**

- Inside the library, the struct definitions and their accesses are compiled in the same translation unit with the same names. The library can read and change its own fields, and the layout can be shared between `.c` files.
- The two sample programs are the only user-level code in the tree that depends on internal field names. They are the first place a field rename would break the build.
- The opt-out is decided per translation unit, at the first `mbedtls` header included. The private-access header has an include guard, so the choice is fixed once it is read. If a `.c` file includes a public header before `common.h`, its struct definitions get `private_` names while its later accesses expect real names, and the file fails to compile. The current library sources avoid this by including `common.h` first.
- `library/pk_internal.h:100,112` and `library/ssl_ciphersuites_internal.h` use `MBEDTLS_PRIVATE(...)` in headers that do not set the opt-out themselves. Those names resolve according to whichever translation unit includes them.

**Unverified.** `tests/suites/test_suite_x509write.function:763` and `tests/suites/test_suite_psa_crypto.function:1329` write `MBEDTLS_PRIVATE(...)` directly, but nothing in the tree defines the opt-out for the generated test files. Whether those tests compile depends on whether the generated test translation unit includes `common.h` before any public header. I did not build the tree to check this.