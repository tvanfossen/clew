# Q4 — src — haiku — run 1

Based on my exploration of the mbedtls repository, here's the breakdown:

## Library vs. Everything Else

**Mbedtls's own implementation:**
- **Source code**: 109 C files in `library/` (`library/CMakeLists.txt:13-128` defines the three libraries):
  - `src_crypto` - cryptographic primitives (85+ files including AES, SHA, RSA, ECDSA, PSA crypto, etc.)
  - `src_x509` - X.509 certificate handling (9 files: `pkcs7.c`, `x509*.c`, `x509write*.c`)
  - `src_tls` - SSL/TLS protocol implementation (18 files: `ssl_*.c`, `debug.c`, network code, etc.)

- **Public interface**: 97 header files in `include/`:
  - 74 files in `include/mbedtls/` - main Mbed TLS API (`README.md:41`)
  - 23 files in `include/psa/` - PSA Cryptography API (`include/psa/crypto.h`, etc.)

**Third-party code:**
- `3rdparty/` contains only **9 C files** from two external projects (`README.md:319-324`):
  - Project Everest (Curve25519 / X25519 implementation)
  - p256-m (P256 elliptic curve implementation)
- `framework/` is a git submodule (``.gitmodules``) but is **not checked out** (empty directory)

**Everything else is NOT part of the library:**

| Component | Count | Purpose |
|-----------|-------|---------|
| `programs/` | 76 C files | Example programs, benchmarks, test utilities (`programs/README.md`) |
| `tests/` | 3 C + 94 .function + 140 .data files | 237 test files (test harness + test data) |
| `scripts/`, `cmake/`, `docs/`, `configs/` | Various | Build configuration, documentation source, helper scripts |

**Line count breakdown:**
- Library implementation: ~150,400 lines (`library/*.c/h`)
- Public headers: ~53,300 lines (`include/*.h`)
- Programs: ~34,100 lines
- Tests: ~275,500 lines
- 3rdparty: ~6,000 lines
- **Total repository: ~527,000 lines**

## What the Documentation Build Covers

Per `doxygen/mbedtls.doxyfile:9-10` and `README.md:25-26`:

The Doxygen build (`make apidoc`) documents **only header files** (FILE_PATTERNS = `*.h`):
- `include/` - public headers for all three libraries
- `doxygen/input/` - seven documentation modules (`doc_*.h`) that organize the API
- `tests/include/alt-dummy` - test-specific headers

The build does NOT document:
- C implementation files (`library/*.c`)
- Program examples (`programs/*.c`) 
- Test implementations (`tests/*.c`)

## How Big Is Mbedtls?

**For the library itself** (what ships): **~203,700 lines**
- 109 implementation files (~150k LOC)
- 97 public headers (~54k LOC)

**If you count development artifacts**: ~527,000 lines total (above breakdown)

**In API surface**: **97 public header files** organized into two main APIs:
- Mbed TLS native API (74 headers)
- PSA Cryptography API (23 headers)

If asked "how big is mbedtls," I'd say: **The library itself is ~200k lines across 109 source files and 97 public headers, organized into three linkable libraries (libmbedcrypto, libmbedx509, libmbedtls). The public interface covers symmetric/asymmetric cryptography, X.509, and TLS/DTLS protocols.**

## Gaps

None - the repository structure, documentation configuration, CMake build files, and README all clearly delineate what belongs to the library versus what's auxiliary.
