# Q5 — mcp — haiku — run 1

## Answer

**What Mbed TLS does:**

Mbed TLS is a C library that implements cryptographic primitives (including the PSA Cryptography API), X.509 certificate manipulation, and the SSL/TLS and DTLS protocols. It is designed for embedded systems with a small code footprint. The README states: "Mbed TLS is a C library that implements cryptographic primitives (including the PSA Cryptography API), X.509 certificate manipulation and the SSL/TLS and DTLS protocols. Its small code footprint makes it suitable for embedded systems." `README.md:4`

**Where to start reading:**

1. **README.md** — overview of the library, build systems, and getting started `README.md:1-100`
2. **include/mbedtls/ssl.h** — primary SSL/TLS API with 606 symbols; key entry point functions: `mbedtls_ssl_init()` (initialize context), `mbedtls_ssl_setup()` (configure context), `mbedtls_ssl_handshake()` (initiate TLS handshake) `include/mbedtls/ssl.h`
3. **library/ssl_tls.c** — core SSL/TLS protocol implementation with `mbedtls_ssl_handshake()` as the main entry point `library/ssl_tls.c:4677-4710`
4. **library/psa_crypto.c** — PSA cryptography API implementation; initialize with `psa_crypto_init()` before any cryptographic operations `library/psa_crypto.c:8609`

**Major parts organized in three libraries (with dependencies):**

1. **libmbedcrypto** (174 files, 4690 symbols in library/, 97 header files):
   - **Cryptographic primitives**: AES (`library/aes.c`), RSA (`library/rsa.c`), ECDSA (`library/ecdsa.c`), SHA-256/512 (`library/sha256.c`, `library/sha512.c`), HMAC (`library/hmac_drbg.c`), ChaCha20/Poly1305, Camellia, DES
   - **Elliptic curve cryptography**: `library/ecp.c` with 142 functions and 627 in ecp_curves.c
   - **Big number arithmetic**: `library/bignum.c`, `library/bignum_core.c`, `library/bignum_mod.c`
   - **Random number generation**: CTR-DRBG (`library/ctr_drbg.c`), HMAC-DRBG (`library/hmac_drbg.c`), entropy sources (`library/entropy.c`)
   - **PSA Crypto API implementation**: `library/psa_crypto.c` (155 functions), with submodules for ciphers, AEAD, hashing, MAC, asymmetric operations
   - **Cipher abstraction layer**: `library/cipher.c` and `library/cipher_wrap.c` (174 functions) wrapping individual algorithms

2. **libmbedx509** (X.509 certificate handling):
   - **Certificate parsing/creation**: `library/x509_crt.c` (57 functions), `library/x509_csr.c` (6 functions)
   - **ASN.1 encoding**: `library/asn1parse.c`, `library/asn1write.c` (22 functions)
   - **Key management**: `library/pk.c` (39 functions), `library/pkparse.c`, `library/pkwrite.c`
   - **PKCS standards**: `library/pkcs12.c`, `library/pkcs5.c`, `library/pkcs7.c` (17 functions)
   - **OID database**: `library/oid.c` (39 functions, 231 symbols in header)

3. **libmbedtls** (depends on libmbedx509 and libmbedcrypto):
   - **TLS/DTLS protocol**: `library/ssl_tls.c` (314 functions), with protocol version handlers: `ssl_tls12_client.c` (60 functions), `ssl_tls12_server.c` (74 functions), `ssl_tls13_client.c` (66 functions), `ssl_tls13_server.c` (73 functions)
   - **Message processing**: `library/ssl_msg.c` (135 functions) implementing record layer
   - **Ciphersuite management**: `library/ssl_ciphersuites.c` (232 symbols including cipher definitions) `include/mbedtls/ssl_ciphersuites.h:232`
   - **Session management**: `library/ssl_cache.c`, `library/ssl_ticket.c`
   - **DTLS-specific**: `library/ssl_cookie.c` for cookie validation
   - **Networking**: `library/net_sockets.c` (25 functions) for platform socket abstraction

**Sample programs (80 files, 965 symbols):**
- **SSL/TLS examples**: `programs/ssl/ssl_client1.c`, `programs/ssl/ssl_server.c`, `programs/ssl/ssl_client2.c` (274 symbols), `programs/ssl/ssl_server2.c` (303 symbols)
- **Cryptography demos**: `programs/psa/crypto_examples.c`, `programs/hash/md_hmac_demo.c`, `programs/cipher/cipher_aead_demo.c`
- **Key handling**: `programs/pkey/key_app.c`, `programs/pkey/gen_key.c` (43 functions), RSA/ECDSA signing and verification examples
- **X.509 utilities**: `programs/x509/cert_write.c` (57 functions), `programs/x509/cert_app.c`
- **Fuzzing targets**: 13 fuzz harnesses (`programs/fuzz/`)

**Testing** (44 files, 859 symbols):
- Comprehensive test suite in `tests/` directory
- Includes unit tests, integration tests, and fuzzing frameworks

**Configuration** (13 files, 143 symbols):
- `include/mbedtls/mbedtls_config.h` (142 symbols) — feature configuration with ifdef guards
- Preset configurations in `configs/` for specific use cases

## Coverage

The index covers **527 files** across the entire repository:
- **library/** (174 indexed files, 4690 symbols) — fully covered; cryptographic implementations and protocol handlers
- **include/** (97 indexed files, 4057 symbols) — all public API headers fully indexed
- **programs/** (80 indexed files, 965 symbols) — sample programs fully covered
- **tests/** (44 indexed files, 859 symbols) — test suite covered
- **3rdparty/** (32 indexed files, 454 symbols) — vendored dependencies
- **docs/** (30 indexed files, 12 symbols) — documentation files

The Doxygen-declared scope (`doxygen/mbedtls.doxyfile`) covers header files only (`*.h`) for documentation generation, but the index covers the entire codebase including implementation files (`.c`). The doxygen input is scoped to `../include, input, ../tests/include/alt-dummy`, while the actual index spans the full repository depth.

## Gaps

None identified. The MCP index successfully answered the structural questions directly without requiring source file reads. All major entry points, module organization, and file locations were resolvable from the index.
