# Q4 — mcp — haiku — run 1

## Answer

mbedtls is layered: a core cryptographic library at its center, wrapped by public interfaces, surrounded by test infrastructure and vendored dependencies.

### **The Core Library (What mbedtls Actually Is)**

The implementation lives in `library/`, with **109 C files** containing the cryptographic primitives, SSL/TLS protocol engines, X.509 certificate handling, and the PSA Cryptography API implementation. These 109 files carry **4,690 indexed symbols**. Supporting them is `include/`, with **97 header files** split into two public interfaces: the legacy mbedtls C API (in `include/mbedtls/`) and the PSA Cryptography API (in `include/psa/`). Those headers define **4,057 symbols** as the public contract `library/` implements. Together, `library/` + `include/` = **206 source files** forming the library itself.

The README documents this as three linked libraries built from this code: libmbedcrypto (cryptographic primitives), libmbedx509 (certificate handling), and libmbedtls (the SSL/TLS engine).

### **What the Documentation Covers**

The Doxyfile at `doxygen/mbedtls.doxyfile:9-10` specifies INPUT paths and FILE_PATTERNS:

```
INPUT                  = ../include input ../tests/include/alt-dummy
FILE_PATTERNS          = *.h
```

So the **generated API documentation covers only headers** (the public interface, not the implementation). It includes:
- All files in `include/mbedtls/` (the main public API)
- All files in `include/psa/` (the PSA Cryptography API)
- Alternative test dummy headers in `tests/include/alt-dummy/`

It **does NOT document**:
- The implementation in `library/`
- The programs, test suite, or build scripts

### **Everything Else in the Repository**

- **3rdparty/** (32 indexed files, 454 symbols): Vendored external code—Everest (curve25519 and X25519 implementations) and P256-M (NIST P-256 alternate implementation). Declared and excluded from first-party metrics.

- **programs/** (80 indexed files, 76 C files, 965 symbols): Example programs and utilities—SSL client/server demos, key generation, certificate tools, fuzzing harnesses, benchmarking code.

- **tests/** (44 indexed files, 3 C files, 859 symbols): The test suite's support code (test data, certificate fixtures, SSL test helpers). The actual test scripts are not indexed by extension.

- **configs/** (13 indexed files, 143 symbols): Pre-built configuration profiles for specific use cases (symmetric-only crypto, Suite-B compliance, thread-safe builds, etc.).

- **scripts/** (9 indexed files, 141 symbols): Build automation and configuration helpers (Python and Perl scripts).

- **docs/** (30 indexed files, 12 symbols): Markdown documentation and generated HTML fragments for ReadTheDocs.

### **Repository Scope**

Total indexed: **527 files** (the whole repository).  
Indexed by category:
- library: 174 files, 4,690 symbols
- include: 97 files, 4,057 symbols  
- programs: 80 files, 965 symbols
- tests: 44 files, 859 symbols
- 3rdparty: 32 files, 454 symbols
- configs: 13 files, 143 symbols
- scripts: 9 files, 141 symbols
- docs: 30 files, 12 symbols
- Root (config files): 47 files, 0 symbols

### **How Big Is mbedtls?**

**If asked for a size metric, I'd say: "The library is approximately 109 C implementation files and 97 header files defining two public API surfaces. The documentation build covers only the headers (97 files, 4,057 API symbols). The full repository includes test suites, example programs, and 9 files of vendored external cryptographic implementations, bringing the total to 527 indexed files."**

The metric depends on what you're measuring:
- **Shipped code**: 206 files (library + include)
- **Documented interface**: 97 files (headers only)
- **With tests and programs**: ~200 files
- **Whole repository**: 527 indexed files

## Gaps

None. The index answered all structural questions directly. No source reads were needed.
