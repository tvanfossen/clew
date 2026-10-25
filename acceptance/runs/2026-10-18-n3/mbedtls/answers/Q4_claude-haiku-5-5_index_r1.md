**Short version:** `mbedtls_strerror()` splits the code into a high-level part and a low-level part, and each part is looked up in a `switch` that `scripts/generate_errors.pl` builds from the `#define`s in the public headers. To add a code, you add the `#define` with a doc comment in the right header, and regenerate `library/error.c`, which is checked in.

**Runtime path**

```
caller: ret = -0x0020            (e.g. MBEDTLS_ERR_AES_INVALID_KEY_LENGTH)
  │
  └─ mbedtls_strerror(ret, buf, buflen)            library/error.c:792
       ├─ ret = -ret                                   (sign dropped)
       ├─ high = ret & 0xFF80 ──► mbedtls_high_level_strerr()   error.c:174
       │      switch on module codes, e.g. CIPHER, DHM, SSL, X509
       │      returns string, or NULL → "UNKNOWN ERROR CODE (%04X)"
       ├─ special case: SSL fatal alert → return early, no low-level part
       ├─ low  = ret & ~0xFF80 ──► mbedtls_low_level_strerr()   error.c:537
       │      switch on module codes, e.g. AES, ASN1, MD5, NET
       │      returns string, or NULL → "UNKNOWN ERROR CODE (%04X)"
       └─ join: "<high> : <low>" if both present
```

- The 0xFF80 mask splits the value. Each module owns a range of bits, and the two lookup functions cover disjoint sets of modules.
- Both helpers take the sign off themselves as well, so the caller can pass the raw negative value.
- `mbedtls_strerror` always NUL-terminates `buf` and truncates if `buflen` is short.
- If `MBEDTLS_ERROR_C` is off, a dummy version writes an empty string (`error.c:867`).

**Where the switch cases come from**

`library/error.c` is generated from `scripts/data_files/error.fmt` by `scripts/generate_errors.pl`. The script:

1. Globs `include/mbedtls/*.h` and regex-matches lines of the form `#define MBEDTLS_ERR_<MODULE>_<NAME>  -0x....`, with a doxygen description either before (`/** ... */`) or after (`/**< ... */`).
2. Builds the module name from the prefix and sorts it into the low-level list or the high-level list, which are hard-coded at the top of the script.
3. Emits one `case -(MBEDTLS_ERR_...): return "MODULE - description";` per code, wrapped in `#if defined(MBEDTLS_<MODULE>_C)` guards, and writes the result to `library/error.c`.

**Adding a new error code**

1. Pick the module header and add the define in the existing range, with a description, e.g. in `include/mbedtls/aes.h`:
   ```c
   /** Invalid key length. */
   #define MBEDTLS_ERR_AES_INVALID_KEY_LENGTH   -0x0020
   ```
   Rules the generator enforces:
   - Name starts with `MBEDTLS_ERR_` and the value is `-0x` plus hex.
   - Exactly one description, either before or after, not both. Each description must be non-empty.
   - No duplicate numeric values across the headers, or the script dies with "Duplicated error code".
   - The header must be `#include`d by the generated file, or the script reports it.
2. If the code belongs to a new module, add the module name to `@low_level_modules` or `@high_level_modules` in `generate_errors.pl`. Otherwise the script exits with "Do not know how to handle". You may also need an entry in `$define_name` or `$include_name` if the header name or config guard doesn't match the module name.
3. Regenerate `library/error.c`. The build does it too (`library/Makefile:355`, `library/CMakeLists.txt:136`), but the file is tracked in git (`git ls-files library/error.c` lists it), so the regenerated file has to be committed with the header change.
4. `tests/scripts/check-generated-files.sh:135` regenerates the file and compares it, so a stale `error.c` fails CI.

**Caveats**

- I did not run the generator or the check script, so I have not confirmed that the checked-in `error.c` is currently in sync. I also did not check the test suites that exercise `mbedtls_strerror`.
- The index does not cover `scripts/*.pl`, so the generator details above come from reading the script directly, not from the index.