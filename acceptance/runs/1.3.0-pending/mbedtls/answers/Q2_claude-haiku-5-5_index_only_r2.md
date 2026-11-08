**What it accomplishes:** `include/mbedtls/private_access.h` defines `MBEDTLS_PRIVATE(member)`, which wraps struct member names in the public headers (for example `mbedtls_aes_context::MBEDTLS_PRIVATE(nr)` in `aes.h:64`). By default it expands to `private_##member`, so `ctx.nr` no longer compiles and callers must go through the API. Renaming the field makes it a visible break in the source, not a silent one. The index shows the macro only at `private_access.h:15` and `:17`, so the wrapping is a source-level mechanism, not a language access control.

**The gate:** The expansion is controlled by `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

- Not defined (default): `MBEDTLS_PRIVATE(m)` → `private_m`. Outside code cannot reach the field.
- Defined: `MBEDTLS_PRIVATE(m)` → `m`. The real field name is visible.

**Who turns the opt-out on.** The index finds three definition sites:

| Site | Who it is for |
|---|---|
| `library/common.h:132` | The library itself. Internal sources that include it see the real field names. |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` example/test program. |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` example/test program. |

For the two programs, the `#define` sits at the top of the file, before the headers are included. They compile against mbedtls internals, so a field rename or restructure will break them, but external applications will not be affected. For the library, the define makes internal code and any internal helpers (the index shows `mbedtls_cipher_get_iv_size` and `mbedtls_pk_get_type` referencing `MBEDTLS_PRIVATE`) work against the real fields.

For ordinary applications the rule is simple: don't define it. Touching `ctx.field` gets a compile error, and the fix is to use the public accessor, or to accept the internal dependency knowingly.

**Caveats from the index:**
- `MBEDTLS_ALLOW_PRIVATE_ACCESS` is an "undeclared" config symbol: there is no Kconfig entry and no config header recorded for this target. It is a plain preprocessor opt-in, not a managed build option.
- The index doesn't show the conditional enclosing `library/common.h:132`, so I can't confirm whether the library defines it unconditionally.
- I couldn't verify include order from the index. If a library source includes a public header before `common.h`, the macro would expand to `private_` there. Check that directly in the source.