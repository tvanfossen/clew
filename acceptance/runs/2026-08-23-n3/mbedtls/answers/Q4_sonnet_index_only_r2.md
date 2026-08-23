Here's the path a negative return code takes to become text, and what the index can and can't confirm about it.

**The runtime path (confirmed in the index):**

1. Each module header (e.g. `include/mbedtls/cipher.h`) `#define`s its own error codes as negative hex constants, like `MBEDTLS_ERR_CIPHER_FEATURE_UNAVAILABLE` = `-0x6080`. The high byte(s) (`& 0xFF80`) identify the *module*; the low bits identify the specific error within that module — so a code can be a pure high-level code, a pure low-level code, or a combination of both (e.g. a high-level SSL error wrapping a low-level BIGNUM error).

2. The caller passes that `int ret` (and a buffer) to `mbedtls_strerror(ret, buf, buflen)` (`library/error.c:792-860`). Its logic, straight from the body:
   - Negates `ret` if negative (codes are stored/compared as positive magnitudes internally).
   - Masks `ret & 0xFF80` to get the high-level part. If non-zero, calls `mbedtls_high_level_strerr()` and writes that string in (or `"UNKNOWN ERROR CODE (%04X)"` if it returns `NULL`).
   - Special-cases `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`: returns early without a low-level lookup.
   - Otherwise masks `ret & ~0xFF80` to get the low-level part, calls `mbedtls_low_level_strerr()`, and appends `" : <string>"` after the high-level part if both are present.

3. `mbedtls_high_level_strerr()` (`library/error.c:174-535`) and `mbedtls_low_level_strerr()` (`library/error.c:537-790`) are each one giant `switch` over the module's error constants, guarded per-module by `#if defined(MBEDTLS_<MODULE>_C)`, returning a literal string per `case`. Both bodies open with the comment `/* Begin Auto-Generated Code. */` — this is generated code, not hand-maintained.

**What the index can't tell you, and what that gap means for a contributor:**

The generator itself isn't in the index — I searched `scripts/*` and it only lists `.py` files; there's no `generate_errors.pl` or similar showing up, and file search confirms the index only holds files a grammar can parse (C/C++/Python), so a Perl script or a `.fmt` template would be invisible to this tool even if present in the repo. That's an honest gap: I can show you the generated output and its markers, but not the generator's own logic from the index alone — you'd need to read the source tree directly for that.

That said, the auto-generated markers plus mbedtls's well-known convention (documented upstream, not in this index) tell you the mechanical part of what a contributor does:

- **Never hand-edit the `switch` bodies inside `Begin/End Auto-Generated Code`** in `library/error.c` — those two functions are regenerated from a script that scrapes `MBEDTLS_ERR_*` macro definitions and their doc comments out of the module headers.
- **Add the new error code as a `#define`** in the relevant module header (e.g. `include/mbedtls/cipher.h`), following the existing negative-hex-constant convention and giving it a doc comment with the human-readable description text — that description is what the generator lifts into the `case`/`return` string.
- **Re-run the generator** (not indexed here, but it's what stamps `library/error.c` with the new `case`) rather than adding the `case` manually, since the file is regenerated wholesale and a manual edit would either be overwritten or drift from the generator's format.
- Guard the new case with the module's `#if defined(MBEDTLS_<MODULE>_C)` if the header itself is conditionally compiled — consistent with every existing block in both functions.

If you want the exact generator mechanics (field widths, how it parses the doc comment, whether it's Perl or Python), that's a direct-source-read task — the index doesn't carry it.
