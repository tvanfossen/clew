**Short answer:** the string comes from `mbedtls_strerror()` in `library/error.c`, which looks the code up in two generated switch tables. Those tables are built by `scripts/generate_errors.pl` from `#define`s in `include/mbedtls/*.h`. You never edit `error.c` by hand. To add a string, you add a documented `#define` to the right header and regenerate.

**The path, step by step**

```
ret = -0x6300                       (negative code from e.g. mbedtls_cipher_*)
   │
   ▼
mbedtls_strerror(ret, buf, buflen)  library/error.c:792
   │  ret = -ret                    → 0x6300
   │  high = ret & 0xFF80           → module part (CIPHER)
   │  low  = ret & ~0xFF80          → specific error within the module
   ▼
mbedtls_high_level_strerr(ret)      error.c:174   switch on high part
   │   "CIPHER - ..."  or NULL → "UNKNOWN ERROR CODE (%04X)"
   ▼
   (if SSL fatal alert, return here without translating low part)
   ▼
mbedtls_low_level_strerr(ret)       error.c:537   switch on low part
   │   "AES - Invalid key length" or NULL → "UNKNOWN ERROR CODE (%04X)"
   ▼
buf gets "HIGH : LOW" when both exist, truncated to buflen, always NUL-terminated
```

Points worth knowing:

- **Sign is stripped first.** Both lookups and the split work on the magnitude. The `case -(MBEDTLS_ERR_X)` labels in the table are negative constants, but the input has already been negated.
- **Two levels.** High-level codes (CIPHER, DHM, ECP, MD, PEM, PK, PKCS12, PKCS5, RSA, SSL, X509, PKCS7) are the high bits, and their table is `mbedtls_high_level_strerr`. Low-level codes (AES, ASN1, BASE64, … THREADING) are the low bits, and their table is `mbedtls_low_level_strerr`. The module lists are hard-coded at the top of `generate_errors.pl` (lines 36–43).
- **Unknown codes are not silent.** An unmapped code becomes `UNKNOWN ERROR CODE (XXXX)`. That is the signal that a code exists but its table entry is missing, usually because the defining header is not in the generator's input.
- **Config-gated.** Everything sits under `MBEDTLS_ERROR_C`. With it off, `mbedtls_strerror` is a stub that writes an empty string (`error.c:144`).

**How the tables get generated**

1. `generate_errors.pl` scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_\w+ -0x....`. It needs a Doxygen description either before the define (`/** ... */`) or after it (`/*!< ... */`), but not both.
2. It maps each name to a module from the prefix (`MBEDTLS_ERR_AES_*` → `AES`). Module names with special mapping are `MPI→BIGNUM`, `CTR→CTR_DRBG`, `HMAC→HMAC_DRBG`, and `NET→net_sockets.h`.
3. It writes one `case -(NAME): return("MODULE - description");` per code, with `#if defined(MBEDTLS_<MOD>_C)` guards, into `library/error.c` via the template `scripts/data_files/error.fmt`.
4. Regeneration is wired into `library/Makefile:355–360`, `library/CMakeLists.txt:139–144` and `scripts/make_generated_files.bat`. `tests/scripts/check-generated-files.sh:135` fails CI if the committed `error.c` is stale.

**What a contributor has to do to add a new string**

1. **Define the code** in the header for its module (e.g. `include/mbedtls/aes.h` for `AES`), with a unique negative hex value. Use the module's own prefix: `#define MBEDTLS_ERR_AES_FOO -0x0021`.
2. **Document it** with a Doxygen comment before or after the define. The generator dies on a missing or doubled description, and the text becomes the human string after `MODULE - `.
3. **Pick a free value.** The generator dies on duplicate codes.
4. **If it's a new module,** you must also add its name to the `@low_level_modules` or `@high_level_modules` list in `generate_errors.pl`. Otherwise it exits with `Do not know how to handle`. Also make sure the header's filename matches the module name lowercased, or the include check fails.
5. **Regenerate** `library/error.c` through the build (the `error.c` make rule or the cmake target), or run `scripts/generate_errors.pl` from the repo root. Don't edit the generated file.
6. **Verify** with `tests/scripts/check-generated-files.sh`, and add a test that the code's `mbedtls_strerror` output is the expected string. Test suites here assert codes by name, so they won't catch a bad description.

I didn't build or run anything. The walkthrough is from reading the source and the generator, and the index confirmed the call graph.