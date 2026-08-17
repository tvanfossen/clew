# Q5 — src — sonnet — run 1

## What this repo is

**Mbed TLS** (version 3.6.7, `include/mbedtls/mbedtls_config.h:37`) — a C library implementing cryptographic primitives, the PSA Cryptography API, X.509 certificate handling, and the SSL/TLS and DTLS protocols, targeted at embedded systems (`README.md:3`).

## Where to start reading

1. **`README.md:3-5`** — one-paragraph mission statement and pointer to the config file.
2. **`include/mbedtls/mbedtls_config.h`** (4,446 lines) — the master compile-time feature-selection file; nearly every subsystem is gated by a `MBEDTLS_*_C` define declared here. Understanding this file explains why so much of the code is wrapped in `#if defined(...)`.
3. **`include/mbedtls/build_info.h`** — pulls in the config and derives version macros (`MBEDTLS_VERSION_NUMBER`/`STRING`, `include/mbedtls/build_info.h:36-37` per the grep above, actually resolved via `mbedtls_config.h:36-37`).
4. **`library/CMakeLists.txt:13` onward** — the `src_crypto`/x509/tls source lists are the fastest way to see exactly which `.c` files belong to which of the three shipped libraries (see below); more authoritative than eyeballing the directory.
5. **`programs/README.md:1-24`** — sample programs organized by feature area (AES, hash, pk, x509, ssl…), a good tour of the public API surface without reading internals.

## Major parts

**Three build outputs** (`README.md:39-41`, confirmed in `library/CMakeLists.txt:285,297,301`):
- `libmbedcrypto` — cryptographic primitives (no dependency on the other two)
- `libmbedx509` — X.509 certificate parsing/writing (depends on mbedcrypto)
- `libmbedtls` — SSL/TLS/DTLS protocol (depends on mbedx509 and mbedcrypto)

**Directory layout:**

| Path | Role |
|---|---|
| `library/` | 109 `.c` files, ~129,300 lines total (`wc -l library/*.c`) — the implementation of all three libraries |
| `include/mbedtls/` | 74 public headers — one per module (`aes.h`, `ssl.h`, `x509_crt.h`, `bignum.h`, etc.) |
| `include/psa/` | 23 headers — the PSA Crypto API surface |
| `programs/` | Sample/demo/test binaries, subdivided into `aes/`, `cipher/`, `hash/`, `pkey/`, `psa/`, `random/`, `ssl/`, `x509/`, plus `fuzz/`, `test/`, `util/` (`ls programs`) |
| `tests/suites/` | 234 test-suite files (`.function`/`.data` pairs, e.g. `test_suite_aes.*`) — a data-driven test framework, not plain unit tests |
| `3rdparty/` | Two vendored crypto implementations: `everest` (Curve25519/X25519, HACL*-derived) and `p256-m` (a compact P-256 implementation with its own driver entrypoints, `3rdparty/p256-m/p256-m_driver_entrypoints.c`) |
| `docs/architecture/` | Design docs — PSA keystore design, PSA migration notes, TLS 1.3 support notes, thread-safety notes |
| `scripts/` | Python/Perl tooling, notably `scripts/config.py` for programmatically editing `mbedtls_config.h` (`README.md:9`) |
| `framework/` | Git submodule (`mbedtls-framework`, `.gitmodules`) — shared test/build infra, only needed on the `development` branch (`README.md:59`) |
| `cmake/`, `CMakeLists.txt`, `Makefile`, `visualc/` | Three parallel build systems: CMake, GNU Make, Visual Studio (`README.md:35-38`) |

**Within `library/`, by subsystem** (from `ls library/`):
- Symmetric/AEAD ciphers: `aes.c`, `aesni.c`, `aesce.c`, `aria.c`, `camellia.c`, `chacha20.c`, `gcm.c`, `ccm.c`, `des.c`, `cipher.c`/`cipher_wrap.c`
- Hashing/MAC: `md.c`, `md5.c`, `hmac_drbg.c`, `hkdf.c`, `cmac.c`
- Big numbers / ECC: `bignum*.c`, `ecp*.c`, `ecdh.c`, `ecdsa.c`, `ecjpake.c`, `dhm.c`
- Post-quantum-adjacent signatures: `lms.c`, `lmots.c`
- Key/certificate handling: `pk*.c`, `x509*.c`, `pkcs5.c`, `pkcs7.c`, `pkcs12.c`, `pem.c`, `asn1parse.c`/`asn1write.c`
- PSA Crypto driver layer: `psa_crypto*.c` (`psa_crypto.c`, `psa_crypto_aead.c`, `psa_crypto_cipher.c`, `psa_crypto_hash.c`, `psa_crypto_mac.c`, `psa_crypto_rsa.c`, `psa_crypto_ecp.c`, `psa_crypto_ffdh.c`, `psa_crypto_pake.c`, `psa_crypto_slot_management.c`, `psa_crypto_storage.c`, `psa_crypto_se.c`, `psa_its_file.c`)
- SSL/TLS protocol: `ssl_tls.c`, `ssl_msg.c`, `ssl_client.c`, `ssl_tls12_client.c`/`ssl_tls12_server.c`, `ssl_tls13_client.c`/`ssl_tls13_server.c`/`ssl_tls13_generic.c`/`ssl_tls13_keys.c`, `ssl_cache.c`, `ssl_cookie.c`, `ssl_ticket.c`, `ssl_ciphersuites.c`
- Platform/entropy/RNG: `entropy.c`, `entropy_poll.c`, `ctr_drbg.c`, `padlock.c`, `memory_buffer_alloc.c`, `constant_time.c`

## Coverage of this answer

I read: the top-level README, the full top-level directory listing, `library/CMakeLists.txt` (partial — the `src_crypto` list and `add_library` calls only, not the x509/tls lists or the rest of the ~700-line file), file listings (not contents) of `library/`, `include/mbedtls/`, `include/psa/`, `programs/`, `3rdparty/`, `docs/architecture/`, and `tests/suites/`, the first ~40 lines of `include/mbedtls/ssl.h`, version macros from `mbedtls_config.h`, and the start of `programs/README.md`.

I did **not** read: the actual implementation of any `.c` file in `library/` (129K lines, 0% read), the contents of any header beyond a few opening lines, any test-suite `.function`/`.data` file, the `framework/` submodule, `scripts/` contents, or the CMake/Make build logic beyond the library-target declarations. This answer is built from directory structure, file names, and a handful of top-of-file excerpts — enough to map the repo's shape, not its behavior.

## Gaps

- Did not open any single crypto/TLS implementation file to verify behavior — only inferred purpose from filenames and headers.
- Did not confirm the exact contents of `src_x509`/`src_tls` lists in `library/CMakeLists.txt` (only `src_crypto` and the `add_library` lines were checked).
- Did not examine `tests/scripts/`, `.github/`, or CI configuration to describe the test/release process.
- Did not verify whether `include/mbedtls/build_info.h` itself defines the version macros or merely includes `mbedtls_config.h` (grep hit came from `mbedtls_config.h:36-37`, cited above; I did not separately confirm `build_info.h`'s own content beyond referencing it).
