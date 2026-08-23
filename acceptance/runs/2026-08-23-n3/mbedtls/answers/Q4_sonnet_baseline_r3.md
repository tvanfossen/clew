Here's the path a negative `int` takes to become a string, end to end.

## 1. The runtime path: `mbedtls_strerror()`

Every mbedtls error code is a negative 16-bit-ish value with two independent fields packed into it: a **high-level** part (module like RSA, SSL, CIPHER, PK…) in bits masked by `0xFF80`, and a **low-level** part (a lower-layer primitive like SHA256, BIGNUM, ASN1…) in the remaining bits (`~0xFF80`). A single return value like `MBEDTLS_ERR_RSA_BAD_INPUT_DATA` might carry only a high-level code, while something like `MBEDTLS_ERR_PK_KEY_INVALID_FORMAT` returned from a lower-level SHA failure can carry both, meant to be concatenated into `"PK - ... : SHA256 - ..."`.

`mbedtls_strerror(int ret, char *buf, size_t buflen)` (`library/error.c:792`):

1. Negates `ret` if negative (all codes are compared as positive magnitudes internally).
2. Masks with `0xFF80` → if nonzero, calls `mbedtls_high_level_strerr(ret)`, which does its own `& 0xFF80` extraction and runs a `switch` over `case -(MBEDTLS_ERR_XXX):` arms, returning a literal `"MODULE - description"` string or `NULL`.
3. Writes that (or `"UNKNOWN ERROR CODE (%04X)"` if `NULL`) into `buf` via `mbedtls_snprintf`.
4. Special-cases `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` to bail out early rather than appending a low-level part.
5. Masks with `~0xFF80` for the low-level remainder; if nonzero, calls `mbedtls_low_level_strerr(ret)` (same switch-table pattern) and appends `" : <low-level string>"` after the high-level part.

Both `mbedtls_high_level_strerr` and `mbedtls_low_level_strerr` are just giant `switch` statements over literal string returns — no table lookup, no dynamic formatting per-code, just compiled-in string constants guarded by `#if defined(MBEDTLS_<MODULE>_C)` for every module that's compiled in.

## 2. Where that switch statement comes from — it's generated, never hand-edited

`library/error.c`'s switch bodies are marked `/* Begin Auto-Generated Code. */` ... `/* End Auto-Generated Code. */` (visible around `library/error.c:735` and the equivalent block in `mbedtls_high_level_strerr`). They're produced by `scripts/generate_errors.pl`, which:

1. Reads the template `scripts/data_files/error.fmt` (contains placeholder tokens `HEADER_INCLUDED`, `HIGH_LEVEL_CODE_CHECKS`, `LOW_LEVEL_CODE_CHECKS`).
2. Globs every header in `include/mbedtls/*.h` and regex-matches `#define MBEDTLS_ERR_<NAME> -0x<hex>` pairs together with their Doxygen comment (either `/** ... */` immediately before or `/**< ... */` immediately after the `#define` — exactly one of the two, or the script `die`s).
3. Derives the module name from the `MBEDTLS_ERR_<MODULE>_...` prefix (with a few hardcoded aliases: `MPI`→`BIGNUM`, `CTR`→`CTR_DRBG`, `HMAC`→`HMAC_DRBG`, and multi-header modules like `X509`→`X509_USE,X509_CREATE`), and classifies it into the low-level or high-level module list declared at the top of the script (`@low_level_modules` / `@high_level_modules`).
4. Emits one `#if defined(MBEDTLS_<DEP>_C) ... case -(MBEDTLS_ERR_NAME): return("MODULE - description"); ... #endif` block per contiguous run of same-module codes, into the low-level or high-level accumulator string as appropriate, and builds up the necessary `#include "mbedtls/<module>.h"` list too.
5. Substitutes those three accumulated strings into the `error.fmt` template placeholders and writes the result out to `library/error.c`.
6. As a sanity check, verifies every header that defined an error code actually got included, and fails the run (`exit 1`) if a module name doesn't match anything in the low/high-level lists, or if a code has both/neither a before- and after-comment, or if two codes share the same numeric value.

This generation step is enforced, not optional: `tests/scripts/check-generated-files.sh` re-runs `generate_errors.pl` and diffs the result against the checked-in `library/error.c`, failing CI if they disagree.

## 3. What a contributor actually has to do to add a new error code

```
1. In the relevant include/mbedtls/<module>.h, add:
     /** One-line description of the error. */
     #define MBEDTLS_ERR_<MODULE>_<NAME>   -0x<unused hex value>
   - Pick a hex value not already used anywhere (generate_errors.pl will die
     on a duplicate).
   - The Doxygen comment must be either directly before (/** */) or
     directly after (/**< */) the #define — never both, never neither.
   - If <MODULE> isn't already recognized, add it to @low_level_modules or
     @high_level_modules at the top of scripts/generate_errors.pl (and add
     any needed alias if the module prefix doesn't match its header/library
     name, the way MPI/CTR/HMAC/X509/PEM are aliased today).

2. Regenerate library/error.c:
     ./scripts/generate_errors.pl
   (run from repo root or scripts/; do not hand-edit the auto-generated
   switch blocks in error.c — check-generated-files.sh will catch drift).

3. Commit both the header change and the regenerated error.c.
```

That's the whole mechanism: the human-readable string never lives as a separate authored artifact — it's the Doxygen one-liner already required next to the `#define`, mechanically pulled out and compiled into a switch table. The only judgment calls a contributor makes are the module classification (low-level vs. high-level) and picking an unused code value; everything else — the `#if` guards, the concatenation logic, the header includes — is regenerated deterministically.
