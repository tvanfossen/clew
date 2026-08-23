## Tracing a negative return code to a string

**1. The call site.** A caller holding a negative `int ret` (e.g. from any `mbedtls_xxx_yyy()` API) passes it to:

```c
void mbedtls_strerror(int ret, char *buf, size_t buflen)
```

declared in `include/mbedtls/error.h`, defined in `library/error.c:792-860` (index confirms only this one real definition body, plus the header declaration and a second candidate line 867 — that second one is the `MBEDTLS_ERROR_C`-undefined dummy stub gated by `MBEDTLS_ERROR_STRERROR_DUMMY`, for builds with error strings compiled out).

**2. Splitting the code.** `mbedtls_strerror` negates `ret` if needed, then splits it into two bitfields:
- `ret & 0xFF80` — the **high-level** module code (which subsystem: SSL, X509, PK, CIPHER, etc.)
- `ret & ~0xFF80` — the **low-level** module code (which primitive underneath: AES, MPI, ASN1, etc.)

mbedtls error codes are additive/composable — a failure can carry both a high-level and a low-level component packed into one negative int, which is exactly why there are two separate translators.

**3. The two translator functions**, both in `library/error.c`, both plain `switch` statements over negated `MBEDTLS_ERR_*` constants, each `case` wrapped in `#if defined(MBEDTLS_<MODULE>_C)` so the switch only contains cases for modules actually compiled in:
- `mbedtls_high_level_strerr(int error_code)` — `library/error.c:174-535`
- `mbedtls_low_level_strerr(int error_code)` — `library/error.c:537-790`

Each returns a `const char *` literal (e.g. `"CIPHER - The selected feature is not available"`), or `NULL` if the code doesn't match any compiled-in case.

**4. Assembly.** Back in `mbedtls_strerror`: the high-level string (or `"UNKNOWN ERROR CODE (%04X)"` if `NULL`) is written into `buf` via `mbedtls_snprintf`. If a low-level component also exists, `" : "` is appended, then the low-level string (or its own "UNKNOWN ERROR CODE" fallback) is appended after it — bounded throughout by `buflen`, always null-terminated. One special case: if the high-level code is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` (only when `MBEDTLS_SSL_TLS_C` is enabled), it returns early without appending a low-level part.

So the shape a caller sees is either `"MODULE - description"` or `"MODULE - description : MODULE - description"`.

**5. A gap I can't close from the index.** Both switch bodies open with the comment `/* Begin Auto-Generated Code. */`. That's a strong signal these tables are machine-generated from the `MBEDTLS_ERR_*` `#define`s scattered across the headers — mbedtls repos historically carry a `scripts/generate_errors.pl` for exactly this — but the index doesn't have that file: `scripts/*` only shows 9 indexed files, all `.py`, and a text search for `generate_errors` across both symbols and prose comes back empty. The indexer covers C/C++/Python/Rust; a Perl generator script (if present in this checkout) is invisible to it by construction. I can't verify its exact mechanics from the index — only that the generated-code marker exists in the committed output.

## What a contributor adds

From what the index *can* show — the structure of the two switches and the header declarations — adding a new error code means:

1. **Define the code** as a negative `#define MBEDTLS_ERR_<MODULE>_<NAME>` constant, following the existing bit-layout convention (high-level codes occupy `0xFF80`, low-level codes occupy the complementary bits) so it composes correctly with `mbedtls_strerror`'s split logic.
2. **Add a `case` arm** to whichever of `mbedtls_high_level_strerr` or `mbedtls_low_level_strerr` matches its category (module-owner decides which), inside the correct `#if defined(MBEDTLS_<MODULE>_C)` block, returning a `"MODULE - human description"` string in the same style as its neighbors.
3. Given the `/* Begin Auto-Generated Code. */` marker, the safer real-world path is almost certainly to regenerate that block from source rather than hand-edit it — but since the generator itself isn't in the index, I can't confirm its exact invocation, input list, or whether it's still wired into the build/CI here. That's something to verify by reading the file directly (or checking `scripts/` and any `check-generated-files`-style CI step) rather than something I can assert from the graph.
