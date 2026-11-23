**What it does.** `MBEDTLS_PRIVATE(member)` is a compile-time rename, defined in `include/mbedtls/private_access.h:14-18`:

- Without `MBEDTLS_ALLOW_PRIVATE_ACCESS`, `MBEDTLS_PRIVATE(foo)` expands to `private_foo`. The struct declares the field as `private_foo`, so application code that writes `ctx->foo` fails to compile with "no member named foo".
- With the define, it expands to `foo` and the name is visible again.

It is a hard compile break, not a warning, and it is not access control. Anyone can define the macro. The purpose is to say "this is not API" and to let maintainers rename, reorder or remove fields in a minor release without it counting as an API break. `docs/3.0-migration-guide.md:74` says direct access "is likely to break in a future minor version", and the `ssl.h` note at lines 5159-5169 calls direct access to `ssl->state` deprecated.

**Who it is for.** Mostly the library's own code and a few programs. Applications are the ones who get the rename.

**Where the opt-out is turned on:**

| Location | Effect |
|---|---|
| `library/common.h:132` | Defines the macro for every library TU that includes `common.h`. The three library `.c` files that use `MBEDTLS_PRIVATE` (`ecdh.c`, `md.c`, `x509_crt.c`) all include it first, so their member accesses resolve to real names. |
| `programs/ssl/ssl_server2.c:8` and `ssl_client2.c:8` | Defined before `ssl_test_lib.h`, so the test servers and clients read and write real `ssl` and config fields directly. |

For code in those places, the consequence is that the code is coupled to the real field names. A rename inside `library/` is fine, because the same TU sees the new name. But the two SSL test programs break if the library changes what those fields mean, and that is the coupling the `ssl.h` warning is about.

**Where it is not turned on, and what happens there:** The test suites (`tests/suites/test_suite_x509write.function:763`, `test_suite_psa_crypto.function:1329`) and `programs/ssl/ssl_context_info.c:553-568` write `MBEDTLS_PRIVATE(...)` explicitly without the opt-out. That is the documented "last resort". It works because the header and the usage expand in the same TU, so both resolve to `private_flags` or `flags`, consistently.

Caveat: the three library files depend on `common.h` coming before any header that expands the macro. I checked that they include it first. I did not check every library TU that includes the internal headers, so I can't say the ordering holds everywhere.