I have everything needed. Here's the walk-through.

## Runtime path: negative int → string

1. **The code space.** Error codes are packed 16-bit values in the negative range, split into a *high-level* module field (bits masked by `0xFF80`) and a *low-level* field (`~0xFF80`) — see `include/mbedtls/error.h:17-91`. A single `int` a caller receives, e.g. `-0x2700`, can carry both a high-level code (e.g. an X.509 or PK failure) and a low-level cause code (e.g. an ASN.1 or MPI failure) added together via `MBEDTLS_ERROR_ADD`/`mbedtls_error_add()` (`error.h:107-154`).

2. **`mbedtls_strerror(ret, buf, buflen)`** (`library/error.c:792` in the built file, template at `scripts/data_files/error.fmt:69`) does the assembly:
   - Negates `ret` if negative.
   - If the high-level bits (`ret & 0xFF80`) are non-zero, calls `mbedtls_high_level_strerr()` and writes that string into `buf`.
   - Unless the high-level code was `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` (early-return case), it then appends `" : "` and calls `mbedtls_low_level_strerr()` for the remaining low-level bits, concatenating that string too.
   - Any code it can't recognize becomes `"UNKNOWN ERROR CODE (%04X)"`.

3. **`mbedtls_high_level_strerr()` / `mbedtls_low_level_strerr()`** are plain `switch` statements over `case -(MBEDTLS_ERR_FOO):` mapping to a literal string like `"AES - Invalid key length"` (`error.c:551` onward). These switches are entirely **generated code** — bracketed by `/* Begin Auto-Generated Code. */` / `/* End Auto-Generated Code. */` markers — not hand-maintained.

So: negative int → mask into high/low parts → two generated lookup switches → concatenated strings → truncated into the caller's buffer, always null-terminated.

## Where the generated code comes from

`library/error.c` is not edited directly for its switch bodies. It's produced by `scripts/generate_errors.pl` from:
- **The template** `scripts/data_files/error.fmt`, which has three placeholder lines: `HEADER_INCLUDED`, `HIGH_LEVEL_CODE_CHECKS`, `LOW_LEVEL_CODE_CHECKS`.
- **All `#define MBEDTLS_ERR_*` macros** found by regex-scanning every header in `include/mbedtls/*.h`, paired with whichever Doxygen comment (before or after the `#define`) documents them.

The script buckets each error name's module prefix (e.g. `AES`, `AES` → `AES`, but `MPI`→`BIGNUM`, `CTR`→`CTR_DRBG`, `HMAC`→`HMAC_DRBG` via hardcoded fixups) into either `@low_level_modules` or `@high_level_modules` (both are literal lists at the top of the `.pl` file — a module not in either list makes the script fail loudly with "Error: Do not know how to handle"). It then emits one `#if defined(MBEDTLS_<MOD>_C) ... case -(NAME): return ("MODULE - description"); ... #endif` block per module, substitutes the three placeholders in the template, and writes the result to `library/error.c`.

## What a contributor does to add a new error code

1. **Pick an unused code point** in the layout table documented at the top of `include/mbedtls/error.h` (respecting the module's reserved 16-bit range, and whether it's a high-level or low-level module).
2. **Add the `#define`** in the relevant module header (e.g. `include/mbedtls/foo.h`), following the exact pattern the regex expects:
   ```c
   /** Short description of the failure */
   #define MBEDTLS_ERR_FOO_SOMETHING  -0x1234
   ```
   The Doxygen comment must be *either* immediately before *or* immediately after the `#define` (never both, never neither) — the script `die`s otherwise. If the module prefix (`FOO`) is new, it must also be added to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`, or the script exits with an error.
3. **Regenerate `library/error.c`**: run `scripts/generate_errors.pl` (no args, from repo root or `scripts/`) — this rewrites the auto-generated switch blocks and `#include` guards in place.
4. **Commit the regenerated `library/error.c` alongside the header change.** CI enforces this isn't skipped: `tests/scripts/check-generated-files.sh` re-runs `generate_errors.pl` and diffs the output against what's committed (`check-generated-files.sh:135`), so a hand-edited or stale `error.c` fails the build.
5. Don't hand-edit anything between the `Begin Auto-Generated Code` / `End Auto-Generated Code` markers — it will be silently clobbered next regeneration and diverge from what CI expects.
