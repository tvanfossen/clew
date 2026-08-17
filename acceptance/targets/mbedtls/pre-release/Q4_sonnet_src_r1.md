# Q4 — src — sonnet — run 1

Now I have what I need.

## Answer

**What's the library, and what's everything else**

mbedtls's own implementation and public interface are two directories:

- `include/` — the public API: `include/mbedtls/*.h` (74 headers, `include/mbedtls/mbedtls_config.h` is the feature-selection file — `README.md:9`) and `include/psa/*.h` (23 headers, the PSA Cryptography API surface). 99 header files total, 53,307 lines (`find include -name "*.h" | xargs wc -l`).
- `library/` — the implementation: 109 `.c` files + 65 `.h` files (internal headers), 150,412 lines total (`find library -name "*.c" -o -name "*.h" | xargs wc -l`).

That's it for "mbedtls itself" — `README.md:4` describes the project as "a C library that implements cryptographic primitives … X.509 certificate manipulation and the SSL/TLS and DTLS protocols," and the CMake build treats `include/` and `library/` as the two subdirectories that make up the actual library target (`CMakeLists.txt:327`, `CMakeLists.txt:331`).

Everything else in the checkout is support machinery, not the library:

- **`3rdparty/`** — vendored code, explicitly called out as not Mbed TLS's own: Project Everest (`3rdparty/everest/`) and p256-m (`3rdparty/p256-m/p256-m/`), under their own licenses (`README.md:321-323`). 38 files (9 `.c`, 17 `.h`).
- **`framework/`** — a git submodule (`.gitmodules:1-3`), not checked out in this clone (empty directory on disk).
- **`programs/`** (76 `.c` files) — example/demo CLI programs, not the library.
- **`tests/`** (97 test-related files) — the test suite.
- Everything else — `docs/`, `scripts/`, `configs/`, `cmake/`, `pkgconfig/`, `visualc/`, `ChangeLog*`, top-level `.md` files, `CMakeLists.txt`, `Makefile` — is build tooling, docs, or metadata.

**What the doc build actually covers**

`doxygen/mbedtls.doxyfile` is the doc build config. Its `INPUT` line is:

```
INPUT = ../include input ../tests/include/alt-dummy
```
(`doxygen/mbedtls.doxyfile:9`)

and `FILE_PATTERNS = *.h` (`doxygen/mbedtls.doxyfile:10`), `RECURSIVE = YES` (`doxygen/mbedtls.doxyfile:11`). So the generated API docs cover:
- `../include` (the public `mbedtls`/`psa` headers — the actual API surface being documented),
- `doxygen/input/*.h` — hand-written doc-only headers with no corresponding code (`doc_mainpage.h`, `doc_ssltls.h`, `doc_x509.h`, `doc_hashing.h`, `doc_encdec.h`, `doc_rng.h`, `doc_tcpip.h` — these exist purely to hold Doxygen `@addtogroup`/mainpage prose),
- `../tests/include/alt-dummy` — dummy alternative-implementation headers used so alt-impl hooks show up in the docs.

Critically, **`library/*.c` is never in `INPUT`, and `FILE_PATTERNS = *.h` means no `.c` file would be picked up even if it were.** The doc build documents the *interface* only — it says nothing about the implementation. `EXTRACT_ALL/EXTRACT_PRIVATE/EXTRACT_STATIC = YES` (`doxygen/mbedtls.doxyfile:5-7`) just means it's thorough about extracting everything declared in those headers, not that it reaches into `library/`.

**The number I'd give**

If asked "how big is mbedtls," I'd give **two numbers, not one**, because "the library" and "the checkout" aren't the same thing and conflating them overstates what's actually mbedtls's own code:

- **~204K lines of C across 174 first-party files** — 150,412 lines / 109 `.c` + 65 `.h` in `library/`, plus 53,307 lines / 99 `.h` in `include/` — and I'd say this counts *mbedtls's own implementation and public API*, nothing vendored, nothing test/tooling.
- Separately, I'd note the doc build's own scope is narrower still: it only documents the 99 headers in `include/` (plus 7 doc-only stub headers), i.e. the *public interface*, not the 109 `.c` implementation files behind it.

I would not fold in `3rdparty/` (38 files, vendored under different licenses), `tests/` (97 files), or `programs/` (76 files) — those are real parts of the checkout but not "mbedtls" in the sense the question is asking, and blending them in would misrepresent library size.

## Gaps

- `framework/` is a submodule not checked out in this clone (`.gitmodules:1-3`), so I could not inspect what it contains or whether it affects the doc build; I'm relying on the doxyfile alone for doc-build scope.
- I did not verify line counts inside `3rdparty/`, `tests/`, or `programs/` since those were explicitly out of scope for "the library" — only file counts were pulled for them.
- I have not confirmed whether `docs/` (Sphinx/ReadTheDocs, `docs/conf.py`) pulls in anything beyond prose `.md`/`.rst` files — it's referenced as "the main Mbed TLS documentation" (`README.md:17`) separately from the Doxygen API-reference build, but I did not trace its build inputs.
