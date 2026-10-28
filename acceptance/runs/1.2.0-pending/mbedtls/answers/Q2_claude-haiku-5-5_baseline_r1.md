**What it accomplishes:** `MBEDTLS_PRIVATE(member)` is a rename, not access control. In `include/mbedtls/private_access.h`, the default expansion is `private_##member`, so `ctx->MBEDTLS_PRIVATE(alg)` becomes `ctx->private_alg`. Outside code that writes `ctx->alg` gets a compile error. The struct definitions stay in public headers, so `sizeof`, stack allocation and layout are still visible. What the macro stops is code depending on the member *names*. That lets the library rename, reorder or retype fields in a minor release without breaking callers who were never supposed to touch them. The 3.0 migration guide (`docs/3.0-migration-guide.md:74`) calls direct access a last resort done "at your own risk", and `include/mbedtls/ssl.h:5163` marks it deprecated.

**Where the opt-out is turned on:** the switch is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. A grep of the tree finds it defined in exactly five places:

| Location | Who it affects |
|---|---|
| `library/common.h:132` | Every library translation unit that includes `common.h` (129 of them). |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` sample, defined before any include. |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` sample, defined before any include. |
| `include/mbedtls/ssl.h` | Mentioned only in a doc comment, not defined there. |

The define in `ssl.h` is prose, not a macro. Only the first three are real opt-outs.

**What that means for the code in those places:** inside the library, `MBEDTLS_PRIVATE(x)` is just `x`, so the library reads and writes its own fields directly. Examples are `library/ecdh.c:150`, `library/md.c:915`, `library/pk_internal.h:100` and `library/x509_crt.c`. The two samples get the same treatment and can reach ssl internals. Because `common.h` is a library-internal header that isn't installed, an external consumer can't pick up the opt-out by accident.

Two details from the tree:

- **The choice is fixed at first inclusion.** `private_access.h` is guarded, so whichever translation unit includes it first decides the mangling. A `.c` file that includes public mbedtls headers before `common.h` would get the `private_` names. The samples avoid this by defining the macro first.
- **Non-opted-out code still compiles.** `programs/ssl/ssl_context_info.c` (lines 553–568) and `programs/fuzz/fuzz_dtlsserver.c:138` use `MBEDTLS_PRIVATE(...)` without the opt-out. They work because the header and the use site mangle to the same `private_` name. The test suites (`tests/suites/test_suite_psa_crypto.function:1329`, `test_suite_x509write.function:763`) use the same spelling. The macro is only broken when some translation unit writes a bare member name against a struct it sees as mangled.