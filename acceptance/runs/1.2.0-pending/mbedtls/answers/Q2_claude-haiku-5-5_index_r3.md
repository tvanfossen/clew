**What it does.** `MBEDTLS_PRIVATE(member)` is a token-paste macro, defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Public headers declare struct members as `MBEDTLS_PRIVATE(state)`, so the member is really named `private_state`. A user writing `ssl->state` gets a compile error. Writing `ssl->MBEDTLS_PRIVATE(state)` works. This is name-mangling, not access control: C has no access control, and the layout is identical either way. What it buys is that accidental use fails at compile time, the intent is visible at every use site, and the library can rename internals without that counting as a source-visible change for most users. It does not give ABI stability by itself. `docs/3.0-migration-guide.md:74` describes the wrapped form as a last resort at the user's own risk.

**Who it is for.** The default is the external user. Only translation units that define `MBEDTLS_ALLOW_PRIVATE_ACCESS` before the first include of `private_access.h` see the real names. In this tree that happens in three places:

| Where | What it means |
|---|---|
| `library/common.h:132` | Defines the opt-out unconditionally. Library `.c` files that include `common.h` first (for example `library/ssl_tls.c:12`, `library/ecdh.c:15`, `library/x509_crt.c:20`, `library/md.c:12`) read and write struct members by their plain names. `common.h` includes only `build_info.h`, `alignment.h` and standard headers, so it does not pull in `private_access.h` before the define. |
| `programs/ssl/ssl_server2.c:8` | Defined before `ssl_test_lib.h`, so the in-tree test server reaches into SSL internals directly. |
| `programs/ssl/ssl_client2.c:8` | Same, for the client. |

For those three places, this means direct member access is allowed and compiles against the in-tree headers. They are built with the library, so an internal rename or layout change breaks them at build time, and the repo's own build is the check. For code outside the tree, the opt-out is off, so it must use `MBEDTLS_PRIVATE(...)` or the public accessors. The `ssl.h:5159-5169` warning on `mbedtls_ssl_handshake_step` says direct state access, even via the wrapper or by defining the macro, is deprecated and may break in any release.

**Caveats.**
- The macro is read at the first inclusion of `private_access.h`. A library `.c` that includes a public header before `common.h` would see the wrapped names. I did not audit include order across every library file, so I can't say there are none. The `library/ssl_ciphersuites_internal.h` header includes `mbedtls/pk.h` before any `common.h`, but it uses the wrapper throughout, so it compiles either way.
- A consumer can also define `MBEDTLS_ALLOW_PRIVATE_ACCESS` in its own translation unit before including mbedtls headers. The header only checks `#ifndef`, so this works, and it is the reason the `ssl.h` warning exists.
- Test suites such as `tests/suites/test_suite_x509write.function:763` use `MBEDTLS_PRIVATE(...)` without the opt-out. Each expansion matches the struct declaration in the same translation unit, so they stay consistent. I did not trace which translation units those test files compile into.