I now have everything grounded to answer confidently.

## What `MBEDTLS_PRIVATE` does

It's a one-line macro in `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Struct fields in public headers are declared as `int MBEDTLS_PRIVATE(nr);` instead of `int nr;` (e.g. `mbedtls_aes_context` in `include/mbedtls/aes.h`). By default that expands the field's real name to `private_nr`. An application written against the public API doesn't know that prefix exists, so `ctx.nr` simply fails to compile — the field is syntactically inaccessible without either the macro or foreknowledge of the mangled name. It's a compile-time access barrier bolted onto C, which has no native `private` keyword, not an ABI or runtime protection (the byte layout is unchanged; anyone who really wants the offset can still get at it).

Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the header flips the macro back to `member`, restoring direct field names. `library/common.h` defines this unconditionally for all of Mbed TLS's own `.c` files, with the comment: *"Although structs defined in header files are publicly available, their members are private and should not be accessed by the user."* So the library's internal code always sees plain field names; only external callers hit the mangled ones.

## Who it's for and why

Per `docs/3.0-migration-guide.md` ("Most structure fields are now private"), this was introduced in the 3.0 API break: as of Mbed TLS 3.x, struct layout is explicitly *not* part of the stable API — fields can be added, removed, reordered, or retyped in any minor release (3.1, 3.2, ...). The macro exists to stop application code from silently depending on layout that the project reserves the right to change, forcing users onto accessor functions (`mbedtls_<module>_get_<field>` / `_set_<field>`) instead. A small set of fields that are contractually stable are left undecorated and documented as public; everything else is wrapped.

There's an explicit, sanctioned escape hatch for cases where no accessor exists yet: an application can `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` itself, or write `bar.MBEDTLS_PRIVATE(foo)` directly, but the migration guide is blunt that this is done "at your own risk" since such code can break on any minor bump (LTS releases like 3.6 are the exception, since they hold ABI stable). `ssl.h` repeats the same warning at `mbedtls_ssl_handshake_step()` around direct access to `ssl->state`, telling users who think they need it to file an issue so a proper accessor can be added instead.

## How widely it's applied

Very broadly — it's essentially universal across the public C headers, not a spot fix for a few sensitive structs. It appears in 59 files under `include/mbedtls/` and `include/psa/` (roughly 872 individual field wrappings), spanning cipher/hash contexts (`aes.h`, `sha256.h`, `gcm.h`, `chacha20.h`, ...), PK/X.509/ASN.1 (`pk.h`, `x509_crt.h`, `x509_csr.h`, `asn1.h`), bignum/ECC (`bignum.h`, `ecp.h`, `ecdsa.h`, `ecdh.h`), DRBG/entropy (`ctr_drbg.h`, `hmac_drbg.h`, `entropy.h`), the SSL/TLS context itself (`ssl.h`), and the PSA crypto layer (`psa/crypto_struct.h`, `psa/crypto_builtin_*.h`, etc.). It's a project-wide convention enforced consistently, not an opt-in applied selectively to a few "sensitive" types.
