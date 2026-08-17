# Q5 — src — haiku — run 1

## Analysis of mbedtls Repository

### What It Does

mbedtls (formerly PolarSSL) is a **C library implementing cryptographic primitives, X.509 certificate handling, and SSL/TLS/DTLS protocol support**, specifically optimized for resource-constrained embedded systems `README.md:4`. It provides:

- **Cryptographic primitives**: AES, RSA, ECC, ChaCha20/Poly1305, hash functions (SHA-256, SHA-512, SHA-3, MD5)
- **Certificate handling**: X.509 certificate parsing, writing, and validation
- **TLS/DTLS protocols**: Full TLS 1.2 and TLS 1.3 implementation, DTLS for datagram transport
- **PSA Cryptography API**: Arm's Platform Security Architecture standard cryptographic interface
- **PSA drivers**: Support for hardware accelerators and secure elements `README.md:305`

The three core libraries are `libmbedcrypto`, `libmbedx509`, and `libmbedtls`, with `libmbedtls` depending on `libmbedx509`, which depends on `libmbedcrypto` `README.md:41`.

### Where to Start Reading

1. **README.md** (`README.md:1-337`) — Overview of build systems, configuration, and architecture
2. **include/mbedtls/ssl.h** (283,286 bytes) — Primary entry point for TLS functionality
3. **include/mbedtls/mbedtls_config.h** (159,124 bytes) — Configuration and feature selection
4. **library/ssl_tls.c** (338,440 bytes) — Core TLS shared functions
5. **library/psa_crypto.c** (330,084 bytes) — PSA Cryptography API implementation
6. **library/CMakeLists.txt** (`library/CMakeLists.txt:1-380`) — Build system showing module organization

### Major Parts

The repository is organized into **three layered libraries** with clear separation:

#### Crypto Layer (libmbedcrypto)
- **Symmetric encryption**: `aes.c`, `aria.c`, `camellia.c`, `chacha20.c`, `des.c`
- **Block cipher modes**: `cipher.c`, `cipher_wrap.c`, `gcm.c`, `ccm.c`
- **Public-key cryptography**: `rsa.c`, `ecp.c` (Elliptic Curve), `ecdsa.c`, `ecdh.c`, `dhm.c`
- **Hash functions**: `sha1.c`, `sha256.c`, `sha512.c`, `sha3.c`, `md5.c`, `ripemd160.c`
- **MACs & KDFs**: `hmac_drbg.c`, `ctr_drbg.c`, `hkdf.c`, `cmac.c`, `poly1305.c`
- **Math primitives**: `bignum.c`, `bignum_core.c`, `bignum_mod.c`
- **PSA layer**: `psa_crypto*.c` files (~7 files implementing the PSA interface)

**Coverage**: 56+ files, ~3,600 public/private function definitions across cryptography domains

#### X.509 Layer (libmbedx509)
- **Certificate parsing**: `x509_crt.c` (105,124 bytes), `x509_csr.c`
- **Certificate creation**: `x509_create.c`, `x509write*.c` files
- **CRL handling**: `x509_crl.c`
- **Key parsing/writing**: `pkparse.c` (43,503 bytes), `pkwrite.c` (20,734 bytes)
- **Public key abstraction**: `pk.c` (54,687 bytes), `pk_wrap.c`
- **ASN.1 support**: `asn1parse.c`, `asn1write.c`, `oid.c`

**Coverage**: ~9 files specializing in certificate/key management

#### TLS Layer (libmbedtls)
- **Protocol versions**: `ssl_tls12_client.c` (135,718 bytes), `ssl_tls12_server.c` (156,853 bytes), `ssl_tls13_client.c` (108,754 bytes), `ssl_tls13_server.c` (128,004 bytes)
- **Core handshake**: `ssl_tls.c` (338,440 bytes), `ssl_msg.c` (239,137 bytes)
- **Key derivation**: `ssl_tls13_keys.c` (66,341 bytes)
- **Session management**: `ssl_cache.c`, `ssl_ticket.c`
- **Networking**: `net_sockets.c` (17,965 bytes)

**Coverage**: ~14 files implementing TLS 1.2 and 1.3 protocols

#### Supporting Infrastructure
- **Configuration**: `mbedtls_config.h` with 70+ compile-time feature flags
- **Build system**: CMake, Make, Visual Studio support with conditional compilation
- **Testing**: 73+ test suites covering all major components (from test suite names in `tests/suites/`)
- **Example programs**: 76 programs in `programs/` directory across SSL, PSA, PKI, hash, random, cipher, and AES categories
- **Third-party integration**: `3rdparty/` includes Project Everest and p256-m for optimized ECC

### Codebase Coverage Summary

| Component | Coverage |
|-----------|----------|
| **Library source** | 109 .c files (~129,300 LoC) + 74 .h public headers (~38,030 LoC) |
| **Test suites** | 73+ named test domains covering crypto, PKI, TLS, PSA, and protocols |
| **Example programs** | 76 .c programs demonstrating SSL/TLS clients/servers, key operations, PSA crypto, cryptographic hashing |
| **Total tracked files** | 431 files (.c/.h) |
| **Configuration** | 1 primary config file with 70+ feature flags, plus 6 config-adjustment headers |
| **Build systems** | CMake (primary, with 3 supporting platforms: Make, Visual Studio, MSVC) |

The repository is **horizontally complete** across cryptographic domains (symmetric, asymmetric, hashing) and **vertically complete** through TLS implementation stacks. Code organization mirrors the three-library dependency graph exactly.

## Gaps

- **Functional completeness of specific algorithms**: While all major algorithms are present, I did not enumerate every curve, cipher, or hash variant supported. `include/mbedtls/ecp.h` references 69,358 bytes of curve definitions, but I did not extract the specific list.
- **PSA driver architecture**: The PSA driver model is mentioned as "work in progress" `README.md:305`, but I did not trace the full driver dispatch mechanism or how external accelerators are integrated.
- **Test data structure**: Tests use `.data` and `.function` file pairs generated by Python/Perl scripts (`tests/suites/*.data`), but I did not analyze the test case format or execution harness.
- **Performance characteristics**: No analysis of constant-time implementations, side-channel resistance measures, or timing-attack mitigations, though `constant_time*.c` files exist.
- **Documentation generation**: Doxygen configuration exists (`doxygen/`), but I did not validate whether all public APIs carry doxygen annotations.
