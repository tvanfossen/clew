**What it accomplishes:** `MBEDTLS_PRIVATE(member)` is a macro that renames a public struct field so ordinary code can't reach it by name. `include/mbedtls/private_access.h` (lines 14–18) does this:

- Default: `#define MBEDTLS_PRIVATE(member) private_##member`. A field `foo` is spelled `private_foo`, so `ctx.foo` fails to compile. Application code that touches a field directly breaks at build time instead of silently depending on the layout.
- With `MBEDTLS_ALLOW_PRIVATE_ACCESS` defined: `#define MBEDTLS_PRIVATE(member) member`, so the real name is used.

The field declarations are written as `MBEDTLS_PRIVATE(foo)`, so the rename is the only thing that changes between the two modes. The member documentation in headers such as `ssl.h`, `bignum.h` and `psa/crypto_struct.h` still describes these fields, but the fields are not a stable interface. That lets the library change layouts without an API break.

**For whom:** the default protects external consumers. The opt-out is for code inside the tree:

- **`library/common.h:132`** defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` (empty). Library sources that include it get direct field access.
- **`programs/ssl/ssl_client2.c:8`** and **`programs/ssl/ssl_server2.c:8`** define it at the top of the file, so these sample programs read and write SSL context fields by name.

Nothing in `mbedtls_config.h` or the Kconfig layer declares the symbol, so it is not a build option. It is a source-level switch that each internal translation unit has to turn on itself.

**What that means for those files:** they are coupled to field names and layout. A rename or reordering inside `ssl.h` or `pk.h` will break them without a public-API change. Code outside those files that defines the macro, or includes `library/common.h` first, gets the same access and the same coupling.

**Caveats:**
- The index doesn't record include order. Whether `library/common.h` is always included before the public headers in library `.c` files, which the opt-out relies on, I can't confirm from the index alone.
- The index lists `mbedtls_cipher_get_iv_size` and `mbedtls_pk_get_type` as referencing `MBEDTLS_PRIVATE`. The `mbedtls_pk_get_type` body I retrieved (`library/pk.c:1593`) doesn't use it, so that reference edge is either in a different declaration or is noise. I didn't verify the cipher one.
- The 3.0 migration guide (`docs/3.0-migration-guide.md`) describes `bar.MBEDTLS_PRIVATE(foo)` as a last-resort way for external code to reach a field. That is consistent with the mechanism above, but it is an escape hatch the docs discourage, not a supported API.