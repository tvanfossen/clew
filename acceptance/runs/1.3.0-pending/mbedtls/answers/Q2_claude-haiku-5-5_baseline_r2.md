**What it does.** `MBEDTLS_PRIVATE(member)` is defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

By default, the field is renamed to `private_<name>`. Code that writes `ctx->md_info` fails to compile, while `ctx->MBEDTLS_PRIVATE(md_info)` still works inside the library. It is a naming gate, not a real access control. Its purpose is to keep struct internals out of the public API. Fields in public headers like `md.h:124` can then change or be removed without breaking applications, and anyone who reaches for a field gets a compile error that points at the boundary. `docs/3.0-migration-guide.md:74` describes the escape hatch as a "last resort… at your own risk", and the warning in `ssl.h:5163` calls direct access to `ssl->state` deprecated and possibly broken in any release.

**Who it is for.** The intended users are the library's own translation units, and the opt-out is what makes that work.

- **`library/common.h:132`** defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally. Its doc comment says the library may access its structs' private members. 129 library files include `common.h`, so the whole library compiles with the real field names. Library `.c` files such as `md.c:12` and `ssl_tls.c:12` include `common.h` before the public headers, so the macro is set before `private_access.h` is first read. Ordering matters: a file that included a public header first would get the renamed fields.
- **`programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8`** define it at the top of the file, before `ssl_test_lib.h`. These test and demo programs are the only ones that opt out directly. They reach into SSL context internals, which is the case the `ssl.h` warning discourages. The define applies only to that translation unit.

**What this means for those places.** Code under `library/` and these two programs can read and write struct fields that external users cannot. Changing those fields is not an API break as far as the library is concerned, because they are internal. Outside those files, code that wants a field must use an accessor, or define the macro itself and accept that the access is unsupported.

**What I did not verify.** `tests/suites/*.function` (e.g. `test_suite_x509write`, `test_suite_psa_crypto`) use `MBEDTLS_PRIVATE`, and I did not trace whether the generated test `.c` files pull in `common.h` or define the macro themselves. If they do not, those suites are compiled against the renamed fields and would have to use the wrapper, which is consistent with what they contain.