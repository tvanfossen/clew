I now have a complete picture. Here's what's going on:

## The mechanism

`include/mbedtls/private_access.h` defines a two-line trick:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Struct declarations in the public headers write fields as `int MBEDTLS_PRIVATE(state);` which the preprocessor expands to `int private_state;`. Anyone outside the library who writes `ctx.state` gets a normal compile error, because the field is actually named `private_state`. There's no runtime cost and no encapsulation in the C sense (it's still a plain public struct member, just under a name application code isn't supposed to know) — it's a compile-time tripwire, not real access control.

The library itself (and anything that legitimately needs raw access) escapes the tripwire by `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` **before** including any mbedtls header. `library/common.h:132` does exactly this, so every `.c` file in `library/` compiles with real field names and full access to its own structs. `programs/ssl/ssl_client2.c` and `ssl_server2.c` also define it, since those reference programs intentionally poke at internals for testing/demo purposes.

## What it accomplishes, and for whom

Per `docs/3.0-migration-guide.md:62-74`, this is the enforcement mechanism for the Mbed TLS 3.0 policy decision: **struct layout is not part of the stable API.** The layout of e.g. `mbedtls_ssl_context` or `mbedtls_rsa_context` can change field order, size, or presence between minor versions (3.1, 3.2, ...) without that being a breaking change, because no external caller is supposed to be touching fields directly — only the accessor functions (`mbedtls_<module>_get_<field>` / `_set_<field>`) are the stable, documented surface.

So it's for **application developers linking against mbedtls as a library**: it converts what used to be a silent ABI/API break (a struct reshuffle that changes behavior or corrupts memory if you'd been poking a field directly) into a compile error at your call site the moment you upgrade mbedtls, rather than a runtime bug. It's a migration/API-boundary enforcement tool, not a security or memory-safety control — `MBEDTLS_ALLOW_PRIVATE_ACCESS` is deliberately provided as an escape hatch ("at your own risk", explicitly documented as likely to break in future minor releases) for people who need something the accessor API doesn't yet expose.

A small number of fields are intentionally left *unwrapped* (genuinely public, documented as stable) — the migration guide calls these out as the exception, not the rule.

## How widely it's applied

It's pervasive across the public API surface: 617 occurrences of `MBEDTLS_PRIVATE(` across the headers in `include/mbedtls/`, spanning 59 header files. It's concentrated in the modules with the biggest/most complex context structs — `ssl.h` alone has 209 wraps (the `mbedtls_ssl_context`/`mbedtls_ssl_config` structs are huge), followed by `cipher.h` (44), `x509_crt.h` (35), `ecdh.h` (24), `lms.h` (20), `rsa.h`/`pkcs7.h`/`ecp.h` (18 each), and a long tail down through `ssl_ticket.h`, `pk.h`, `ecjpake.h`, `ssl_cache.h`, `entropy.h`, `ccm.h`, `ssl_ciphersuites.h`, etc.

On the consuming side, only `library/common.h` needs to opt out for the whole library build (every library `.c` file includes it and inherits the `#define`), plus the two SSL demo/test programs that intentionally reach into internals. Everything else in `tests/` and `programs/` goes through the public accessor functions like ordinary external code would — which also means the test suite doubles as coverage that the accessor API is actually sufficient, not just that the private-field tripwire compiles.
