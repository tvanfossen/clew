I now have what I need, grounded in the actual source.

## What `MBEDTLS_PRIVATE` is

```c
// include/mbedtls/private_access.h
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

It's a token-pasting macro used as a wrapper around struct field names in public headers, e.g. in `gcm.h`:

```c
uint64_t MBEDTLS_PRIVATE(len);   // expands to either "private_len" or "len"
```

By default (`MBEDTLS_ALLOW_PRIVATE_ACCESS` undefined), every wrapped member gets renamed with a `private_` prefix. If an application defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` **before** including the header, the macro becomes a no-op and the real field name is exposed.

## What it accomplishes, and for whom

This was introduced for the Mbed TLS 3.0 API break (documented in `docs/3.0-migration-guide.md`). Struct layouts in mbedtls's public headers have always been visible (C has no real encapsulation — the struct has to be a complete type so callers can stack-allocate it), but the project wants those fields treated as implementation detail, not API. Renaming every field to `private_foo` is a compile-time speed bump: application code that does `ctx.len` instead of calling `mbedtls_gcm_...()` accessor functions simply fails to compile, with an error pointing at the missing member — forcing the developer to either find the accessor function or explicitly opt in via `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`.

So it's aimed at:
- **Application developers**, who are pushed toward the accessor-function API (`mbedtls_<module>_get/set_<field>`) instead of poking struct internals directly, which the migration guide explicitly documents as "at your own risk... likely to break in a future minor version."
- **The Mbed TLS maintainers themselves**, who get freedom to reorder/rename/resize struct internals across minor releases without it counting as a source-compatibility break for well-behaved callers — a real constraint given the library also promises API stability within a major version and ABI stability within an LTS branch (3.6 LTS is called out specifically in the migration guide as safer to break this convention in, since ABI is more tightly held there).

It is explicitly not a security or memory-safety mechanism — nothing stops a determined caller from defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` or reaching into the struct anyway; it's a compiler-enforced "please don't" for anyone who hasn't opted out of the guardrail.

## How widely it's applied

Very widely — it's a blanket convention, not spot treatment. It appears in **872 occurrences across 57 header files**, essentially every public struct with internal state in both the legacy crypto/X.509/TLS API and the newer PSA headers:

- Crypto primitives: `aes.h`, `aria.h`, `camellia.h`, `chacha20.h`, `chachapoly.h`, `cmac.h`, `des.h`, `gcm.h`, `ccm.h`, `nist_kw.h`, `poly1305.h`, `sha1.h`, `sha256.h`, `sha3.h`, `sha512.h`, `md5.h`, `ripemd160.h`, `md.h`, `cipher.h`, `block_cipher.h`
- Public-key / big-number: `bignum.h`, `rsa.h`, `ecp.h`, `ecdh.h`, `ecdsa.h`, `ecjpake.h`, `dhm.h`, `pk.h`
- RNG/entropy: `ctr_drbg.h`, `hmac_drbg.h`, `entropy.h`
- X.509/ASN.1: `asn1.h`, `x509.h`, `x509_crt.h`, `x509_crl.h`, `x509_csr.h`, `pem.h`, `pkcs7.h`, `oid.h`
- TLS: `ssl.h`, `ssl_cache.h`, `ssl_ciphersuites.h`, `ssl_cookie.h`, `ssl_ticket.h`
- Platform/misc: `platform.h`, `threading.h`, `timing.h`
- PSA layer: `psa/crypto_struct.h`, `crypto_builtin_composites.h`, `crypto_builtin_key_derivation.h`, `crypto_driver_contexts_key_derivation.h`, `crypto_extra.h`, `crypto_platform.h`, `crypto_se_driver.h`, `crypto_types.h`, `crypto_values.h`

Internally, the library obviously needs unrestricted access to its own structs, so `library/common.h` (included by essentially all `.c` files in `library/`) unconditionally `#define`s `MBEDTLS_ALLOW_PRIVATE_ACCESS` before pulling in any mbedtls headers, with a comment explicitly noting "Although structs defined in header files are publicly available, their members are private and should not be accessed by the user." The two interactive test programs `programs/ssl/ssl_server2.c` and `ssl_client2.c` do the same at the top of the file, since they intentionally exercise internal fields for testing purposes.
