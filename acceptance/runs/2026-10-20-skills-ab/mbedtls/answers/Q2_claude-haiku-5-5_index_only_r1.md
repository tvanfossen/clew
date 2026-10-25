**What it does.** `MBEDTLS_PRIVATE(member)` is a rename, not an access check. In `include/mbedtls/private_access.h`, when `MBEDTLS_ALLOW_PRIVATE_ACCESS` is not defined (lines 14–16), it expands to `private_##member`. So `mbedtls_aes_context`'s `nr` field is really `private_nr`, and code that writes `ctx->nr` fails to compile. When the opt-out is defined (lines 16–18), it expands to the bare `member`, and the same spelling compiles. The wrapper is applied to fields in public headers, for example `mbedtls_aes_context` in `aes.h`, `mbedtls_aria_context` in `aria.h`, `mbedtls_asn1_named_data` in `asn1.h`, and the PSA key-ID accessors in `psa/crypto_values.h`.

**For whom.** The default protects application developers who include the public headers. Their code can't reach into library internals, so the library can change field layout or meaning without breaking them. Library code gets the same protection plus a way out: it writes `ctx->MBEDTLS_PRIVATE(nr)` and gets whichever form the build selects. The index shows `mbedtls_cipher_get_iv_size` and `mbedtls_pk_get_type` referencing the macro this way.

**Where the opt-out is turned on.** The index shows `MBEDTLS_ALLOW_PRIVATE_ACCESS` defined in three places:

| Site | Who it is for |
|---|---|
| `library/common.h:132` | Library translation units that include it. Their direct field access compiles, so they are coupled to struct layout. |
| `programs/ssl/ssl_client2.c:8` | The SSL test client, which reaches into TLS internals. |
| `programs/ssl/ssl_server2.c:8` | The SSL test server, same reason. |

For those files, field renames in the structs are silent to the compiler and only fail at link or runtime. Any change to those fields has to be checked against these sites, not only the public API.

**Limits of what I could confirm.**
- The index has the define lines but not the surrounding `#if` context in `common.h`, so I can't say whether it is unconditional there.
- Whether the define in the two programs precedes the include of `private_access.h` is not shown. For it to take effect it must, and line 8 suggests it does.
- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` and does not record the repository's own config header. The default state of the opt-out in a normal build is therefore not established here.