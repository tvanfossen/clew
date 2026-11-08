**What it accomplishes:** `MBEDTLS_PRIVATE(x)` is a name-mangling wrapper around struct members. In `include/mbedtls/private_access.h`, the macro is gated on `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

- **Default (opt-out not defined):** `MBEDTLS_PRIVATE(member)` expands to `private_##member`. So `mbedtls_aes_context` declares `nr`, `rk_offset` and `buf` as `private_nr`, `private_rk_offset` and `private_buf` (`include/mbedtls/aes.h:64-71`). Outside code that writes `ctx.nr` or `ctx->nr` fails to compile. The public header is still visible, but the fields are not usable by name.
- **Opt-out defined:** the same macro expands to plain `member`, so the names are ordinary.

The 3.0 migration guide describes this as the intent: "Most structure fields are now private… Attempting to access a private field directly will result in a compilation error" (`docs/3.0-migration-guide.md`, "Most structure fields are now private"). The header's own doc says it is a "Macro wrapper for struct's members." The intent is to stop applications from depending on internal layout, so the library can change struct fields without breaking the ABI or API.

**Who the opt-out is for:** `MBEDTLS_ALLOW_PRIVATE_ACCESS` is not a Kconfig option. It is a bare macro that a translation unit defines to see the plain names. Its documented purpose is in `library/common.h:132`: "Allow library to access its structs' private members. Although structs defined in header files are publicly available, their members are private and should not be accessed by the user."

The index shows it being turned on in three places:

| Location | What it means |
|---|---|
| `library/common.h:132` | The library's internal utilities header, so library sources that include it get plain member names. |
| `programs/ssl/ssl_client2.c:8` | The sample client reads TLS internals directly. |
| `programs/ssl/ssl_server2.c:8` | The sample server does the same. |

For the code in those places, `ctx->nr` and similar accesses compile, and they stay coupled to the struct layout. Application code outside the library and these two sample programs still gets the mangled names and cannot touch the fields.

**Limits of what I could confirm from the index:**
- Whether `library/common.h:132` is unconditional, or defined only in some library builds, is not visible to me. The index records the definition and its line but not its surrounding conditions. Check this before relying on "all library sources."
- For `ssl_client2.c` and `ssl_server2.c`, the index gives line 8 but not the include order. I did not verify that the define comes before the mbedtls includes, which it must for the opt-out to take effect.