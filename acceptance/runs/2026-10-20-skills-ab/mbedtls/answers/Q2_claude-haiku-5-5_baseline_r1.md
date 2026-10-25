**What it accomplishes.** `MBEDTLS_PRIVATE(m)` is a rename, not an access control. In `include/mbedtls/private_access.h:14-18`, it expands to `private_##m` by default and to plain `m` only when `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined. Struct declarations in the public headers are written with the same macro, so the field is really named `private_m` for an outside user. A plain `ctx->state` then fails to compile, while `ctx->MBEDTLS_PRIVATE(state)` still resolves, because both sides expand the same way.

I checked this with a two-line probe. Without the define, `ssl->MBEDTLS_PRIVATE(state)` compiles and `ssl->state` fails with "has no member named 'state'". With the define, both compile.

The purpose is to keep field names and layout out of the supported API, so Mbed TLS can change internals in a minor release. The migration guide (`docs/3.0-migration-guide.md:74`) calls direct access a last resort "at your own risk". `ssl.h:5163` marks it deprecated.

**For whom: where the opt-out is turned on.**

| Where | What it means |
|---|---|
| `library/common.h:132` | The library's own translation units. Most `library/*.c` files include `common.h` (107 of 109), so they get raw member access to every struct. |
| `programs/ssl/ssl_server2.c:8` | The in-tree test server, which defines the macro itself before any include. |
| `programs/ssl/ssl_client2.c:8` | The in-tree test client, same pattern. |

So the opt-out is for the library and its own test tools, not for application code. Inside the library, `ssl->state` and `ssl->MBEDTLS_PRIVATE(state)` mean the same thing, so library code is not visibly "using the escape hatch".

**Two things to be aware of:**

- **Include order matters.** `common.h` has to be included before any public Mbed TLS header. Otherwise the struct is declared as `private_m` while the library code reads `m`, and the build breaks. Checked: `library/ssl_tls.c`, `rsa.c` and `ecp.c` all include `common.h` first. I did not check every file.
- **`programs/ssl/ssl_context_info.c` is not an opt-out user.** It reads `ciphersuite_info->MBEDTLS_PRIVATE(flags)`, `(cipher)` and `(mac)` at lines 553-568, but does not define `MBEDTLS_ALLOW_PRIVATE_ACCESS`. It compiles because it uses the macro consistently, so it is the documented "last resort" pattern, not a bypass. Nothing in the tree defines the define for it.

Two files, `library/ecp_curves_new.c` and `library/ssl_debug_helpers_generated.c`, do not include `common.h`. I did not check whether they touch struct members.