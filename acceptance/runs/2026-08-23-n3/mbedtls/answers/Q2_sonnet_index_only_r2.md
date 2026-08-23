This is a clean, fully-answerable question from the index — the macro definition, its gating, and every `#define` site of the opt-out all showed up directly.

**Mechanism.** `include/mbedtls/private_access.h` defines `MBEDTLS_PRIVATE(member)` as an `#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS` / `#else` pair:

- if `MBEDTLS_ALLOW_PRIVATE_ACCESS` is **not** defined, `MBEDTLS_PRIVATE(member)` expands to `private_##member` — i.e. it renames the field in the declarator to `private_member`.
- if it **is** defined, it expands to plain `member` — the real field name.

Every public struct field in the headers (`aes.h`, `bignum.h`, `ssl.h`, `rsa.h`, `gcm.h`, `ccm.h`, `psa/crypto_struct.h`, etc. — the index shows 482 wrapped fields across the tree) is declared as `MBEDTLS_PRIVATE(fieldname)`. So by default an external caller who writes `ctx.nr` or `ctx.reseed_counter` gets a compile error: the real member is actually named `private_nr`, not `nr`. It's a source-level access-control trick, not a real C `private` — nothing stops a determined caller from writing `ctx.private_nr` directly, but it does stop accidental/naive field access and signals "this is not part of the ABI/API contract."

**Who it's for, concretely — the opt-out is turned on in exactly three places the index finds:**

1. **`library/common.h:132`** — `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`. This is the internal library-wide header included by essentially all of `library/*.c`, so **the library's own implementation code** sees real field names (`nr`, `reseed_counter`, etc.) and can access them directly, because internal code is exactly the code that's supposed to reach into struct internals.
2. **`programs/ssl/ssl_client2.c:8`**
3. **`programs/ssl/ssl_server2.c:8`**

These two sample/test programs individually `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the headers, opting themselves back into raw field access — evidently because they need internals for test/debug instrumentation that the public API doesn't expose.

**What it means concretely:** everyone else — application/user code, and any other program in `programs/` that doesn't define the macro — sees only `private_*`-prefixed members and is expected to use accessor functions instead of touching fields (this is exactly what `docs/3.0-migration-guide.md`'s "Most structure fields are now private" section documents, including the documented last-resort escape hatch of writing `bar.MBEDTLS_PRIVATE(foo)` yourself if you must). The library's own `.c` files and these two test-driver programs are the only code in this tree granted the "I know what I'm doing" opt-out; that's a small, explicit allowlist, not a broad default.
