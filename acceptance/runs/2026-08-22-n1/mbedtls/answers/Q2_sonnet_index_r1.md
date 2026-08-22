Now I have enough grounded detail to answer.

## What `MBEDTLS_PRIVATE` does

It's a build-time name-mangling trick, defined in `include/mbedtls/private_access.h`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Every struct field mbedtls wants to reserve is declared in the header as `int MBEDTLS_PRIVATE(foo);`, which the preprocessor expands to `int private_foo;`. Any application code that tries to write `ctx.foo` directly gets a **compile error**, because the real field name is `private_foo`, not `foo` — there's no such member. The only way in is to either use the module's accessor functions (`mbedtls_<module>_get_foo()`/`set_foo()`), or, as an explicit last resort, spell it out as `ctx.MBEDTLS_PRIVATE(foo)` yourself, at your own risk.

Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the headers flips the macro back to a no-op, so `foo` and `MBEDTLS_PRIVATE(foo)` become the same identifier and direct access compiles again.

## Who it's for, and why

This is documented explicitly as an API/ABI-stability boundary, not a security control (`docs/3.0-migration-guide.md`, "Most structure fields are now private"):

- As of mbedtls 3.0, struct layout is no longer part of the stable public API — minor versions (3.1, 3.2, …) are free to add, remove, rename, reorder, or retype fields.
- The mangled name is the enforcement mechanism: it stops application code from silently depending on layout that the project has explicitly said it may change, catching the dependency at compile time rather than letting it become an ABI break discovered at runtime in a later release.
- A small set of fields are documented as genuinely public/stable and aren't wrapped; everything else defaults to private until an accessor is added.

Who gets the bypass:
- **The library itself** unlocks it globally — `library/common.h` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` before pulling in the public headers, with the comment "Although structs defined in header files are publicly available, their members are private and should not be accessed by the user" — so internal library code addresses fields by their plain names as if the wrapper weren't there. (A handful of library files — `ecdh.c`, `md.c`, `x509_crt.c`, `pk_internal.h`, `ssl_ciphersuites_internal.h` — still spell out `MBEDTLS_PRIVATE(member)` explicitly even under that umbrella, which works either way since the macro degrades to identity, but is a minor inconsistency rather than a second mechanism.)
- Sample/test programs that legitimately need raw struct access (e.g. `programs/ssl/ssl_client2.c`, `ssl_server2.c`) `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` at the top of the file, same escape hatch available to any application.
- Everyone else — normal application code linking against mbedtls — is expected to go through accessor functions; the guide points users with a missing accessor to file an enhancement request rather than reach for the macro.

## How widely it's applied

It's applied broadly, not to a handful of "sensitive" structs. 51 public headers under `include/mbedtls/` pull in `private_access.h`, and there are 623 uses of `MBEDTLS_PRIVATE(...)` across those headers — i.e. this is the default posture for struct fields across essentially the whole public API surface (crypto contexts, X.509, SSL/TLS config and connection structs, etc.), not an exception applied selectively.
