**Short answer:** `mbedtls_strerror()` in `library/error.c` splits the code into a high-level part and a low-level part, looks each up in a `switch`, and joins the strings with ` : `. That `switch` is generated, not hand-written, from the `#define`s in `include/mbedtls/*.h` by `scripts/generate_errors.pl`. To add a string, you add the `#define` with a doc comment, register the module if it's new, regenerate `library/error.c`, and add a test row.

## Runtime path

Take `ret = -0x40A0` (RSA bad input + AES invalid key length, from `tests/suites/test_suite_error.data`):

1. **Sign flip.** `ret < 0` is negated, giving `0x40A0`.
2. **High-level part.** `ret & 0xFF80` gives `0x4080`. `mbedtls_high_level_strerr()` switches on it and returns `"RSA - Bad input parameters to function"`.
3. **SSL early exit.** If the high part is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, the function returns after the high-level string and skips the low-level part.
4. **Low-level part.** `ret & ~0xFF80` gives `0x0020`. `mbedtls_low_level_strerr()` returns `"AES - Invalid key length"`.
5. **Join.** If both parts exist, it writes `" : "` and appends the low-level string. The result is `"RSA - Bad input parameters to function : AES - Invalid key length"`.
6. **Unknown codes.** If a switch has no match, that part becomes `UNKNOWN ERROR CODE (%04X)`. A code with no bits in either range produces no output at all.

The split works because high-level modules (RSA, SSL, X509, …) occupy bits `0x0080` and up, while low-level modules (AES, ASN1, MD5, …) must fit in `0x0001`–`0x007F`. Any new low-level code has to respect that range.

## Build-time path

```
include/mbedtls/*.h  (#define MBEDTLS_ERR_X -0x00NN  + /** doc */)
        │
        ▼
scripts/generate_errors.pl  + scripts/data_files/error.fmt (template)
        │
        ▼
library/error.c  (case -(MBEDTLS_ERR_X): return "MOD - doc";)
```

- The generator scans each header with a regex that requires exactly one doc comment (before or after the define, not both). It dies on duplicate values.
- It sorts each code into the low- or high-level `switch` by module name, using `@low_level_modules` and `@high_level_modules`. Unknown modules fail with `Do not know how to handle`.
- CMake regenerates `error.c` when `GEN_FILES` is set. The Makefile has an equivalent rule. `library/error.c` is also tracked in git, and `tests/scripts/check-generated-files.sh` checks it against the generator, so the committed file must match.

## What a contributor does

1. **Pick a free code.** Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x00NN` to the module's header in `include/mbedtls/`. Stay inside that module's `/* Error codes in range … */` block, and use the `-0x` hex form the regex expects.
2. **Write exactly one doc comment.** Put `/** … */` before the define or `/**< … */` after it, not both. The trailing period is stripped, and the text becomes the human-readable description.
3. **New module?** Add its prefix to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. The header must also be included with the matching lowercase name. The generator maps `MPI`→`BIGNUM`, `CTR`→`CTR_DRBG`, `HMAC`→`HMAC_DRBG`, `NET`→`net_sockets`, and it has `define_name` special cases for X509, ASN1, SSL, PEM. Check whether the new module needs one.
4. **Regenerate.** Run `perl scripts/generate_errors.pl` from the repo root, or let the build do it. Don't hand-edit `library/error.c`.
5. **Test first.** Add a row to `tests/suites/test_suite_error.data` in the form `error_strerror:-0x00NN:"MOD - description"`, with a `depends_on:` line if needed. Run it red, then green. The row is what proves the string is reachable.
6. **Changelog.** Use `ChangeLog.d/` only if the change is user-visible. `ChangeLog.d/00README.md` says test data and internal changes don't need an entry. A new error string is a judgment call, so I'd ask the maintainers.

**Not verified:** I read the generator, the template, the tests and the CMake/Makefile rules but did not run the generator, the test suite or `check-generated-files.sh`. The `CONTRIBUTING.md` contents also weren't checked for any extra steps.