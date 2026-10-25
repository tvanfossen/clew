**What it accomplishes.** `MBEDTLS_PRIVATE(member)` is a preprocessor wrapper around struct member names, defined in `include/mbedtls/private_access.h:15`. Its default expansion is `private_##member`, so a field declared as `MBEDTLS_PRIVATE(nr)` is actually named `private_nr` to any translation unit that doesn't opt out. Code outside the library that writes `ctx->nr` fails to compile, which makes the internal layout of structs like `mbedtls_aes_context` (the `nr` field at `include/mbedtls/aes.h:64`) an unstable implementation detail rather than API. The index shows the macro applied across many headers (aes, aria, asn1, block_cipher, and others), so this is a deliberate tree-wide convention.

**Who the opt-out is for.** The switch is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. When it is defined, the macro expands to the plain `member` name, so the field is visible again. The index shows three places that define it:

| Site | Who it covers |
|---|---|
| `library/common.h:132` | The library itself. Internal `.c` files that include the common header see real field names. |
| `programs/ssl/ssl_client2.c:8` | The sample/test client. |
| `programs/ssl/ssl_server2.c:8` | The sample/test server. |

Two of the functions that reference the macro, `mbedtls_cipher_get_iv_size` and `mbedtls_pk_get_type`, appear in the index's `referenced_by` list. I did not read their bodies, so I can't say exactly how they use the fields.

**What that means in those places.** Inside the library and the two ssl sample programs, field access is unchecked. Those translation units can read and write internal members directly, so changing a private field's name or meaning can break them at compile time or silently. For everyone else, the privacy is a compile-time convention: a consumer can define the macro before including the headers and reach the internals. Nothing stops that; the wrapper only makes accidental dependence fail to compile.

**Gaps in what the index shows.**
- Dossier lists the three definition sites above, but the search summary says the switch "gates 2 site(s)". I went with the three.
- The index reports the switch's origin as "undeclared", which I read as meaning no Kconfig or doc declaration backs it. It is a plain preprocessor define.
- I could not tell from the index whether the `#define` at `library/common.h:132` sits inside another conditional. If it is unconditional, every library build gets the opt-out; checking that needs the source.