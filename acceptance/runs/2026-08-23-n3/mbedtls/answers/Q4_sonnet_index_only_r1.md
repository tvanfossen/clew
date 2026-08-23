## The path from a negative `int` to a string

**1. The call site** — any mbedtls function returns a negative `int` (e.g. `MBEDTLS_ERR_CIPHER_BAD_INPUT_DATA`, `-0x6400`). Nothing about the return value itself is a string; it's just a bit-packed code.

**2. The caller invokes `mbedtls_strerror(ret, buf, buflen)`** — declared in `include/mbedtls/error.h`, defined in `library/error.c:792-860`. Body, verified from the index:

- Normalizes sign: `if (ret < 0) ret = -ret;`
- Splits the code into two fields by mask: `ret & 0xFF80` is the **high-level** (module) part, `ret & ~0xFF80` is the **low-level** part. This is why mbedtls error codes are commonly a combination of a module code and a low-level code OR'd together.
- Calls `mbedtls_high_level_strerr(ret)` (`library/error.c:174-535`) if the high-level field is non-zero.
- If a low-level field is also present, appends `" : "` plus the result of `mbedtls_low_level_strerr(ret)` (`library/error.c:537-790`).
- Falls back to `"UNKNOWN ERROR CODE (%04X)"` if either lookup returns `NULL`.
- Writes into `buf`, truncating to `buflen`, always null-terminating (checked explicitly for `buflen == 0`).

**3. The two `strerr` functions are each one giant `switch`** over module/low-level constants — e.g. `mbedtls_high_level_strerr` has cases for `MBEDTLS_ERR_CIPHER_*`, `MBEDTLS_ERR_DHM_*`, `MBEDTLS_ERR_ECP_*`, `MBEDTLS_ERR_MD_*`, `MBEDTLS_ERR_PEM_*`, `MBEDTLS_ERR_PK_*`, etc.; `mbedtls_low_level_strerr` covers `MBEDTLS_ERR_AES_*`, `ARIA`, `ASN1`, `BASE64`, `BIGNUM`, `CAMELLIA`, `CCM`, `CHACHA20`, `CHACHAPOLY`, `CTR_DRBG`, `DES`, `ENTROPY`, and more. Each `case` is wrapped in `#if defined(MBEDTLS_<MODULE>_C)` so a disabled module's error strings simply don't compile in, and each returns a literal like `"CIPHER - Bad input parameters"`.

**4. Config gating.** The whole file is compiled only when `MBEDTLS_ERROR_C` is defined; there's also an `MBEDTLS_ERROR_STRERROR_DUMMY` path (both gate macros are defined in `include/mbedtls/mbedtls_config.h` and the two size-reduced config presets) for builds that want the API present but the strings stripped out.

## The auto-generation seam — and a genuine gap

Both switch bodies open with the literal comment `/* Begin Auto-Generated Code. */`. That's the index telling you these blocks aren't hand-authored line by line — they're generated from the `MBEDTLS_ERR_*` `#define`s (with their `/**< description */` doc comments) in each module's header under `include/mbedtls/`.

I can't verify the generator itself from the index: this repo's index only covers `.c/.h/.inc/.md/.py` files, and mbedtls's error-table generator is conventionally a Perl script under `scripts/` — a `.pl` file, which this index's scope doesn't include at all (confirmed: `scripts/*` lists only 9 `.py` files, no generator script). I checked prose search too and found nothing describing the generation process directly. So take the rest of this paragraph as inference from the "Begin Auto-Generated Code" marker and the file layout, not something I can point at a specific indexed file for.

## What a contributor has to do to add a new error code

1. Add a new `#define MBEDTLS_ERR_<MODULE>_<NAME>  -0x____  /**< description */` in the relevant module header (e.g. `include/mbedtls/cipher.h`), picking an unused bit value within that module's allocated error-code range and writing the doc comment — that comment text is what ends up as the human-readable string.
2. Regenerate `library/error.c` rather than hand-editing the switch cases between the auto-generated markers — a hand edit there will get clobbered the next time the generator runs, and since I can't see the generator invocation from this index, I'd recommend confirming the exact regeneration command (likely `make generated_files` or a `scripts/generate_errors.*` target) by reading the repo/build files directly rather than trusting me to name it.
3. Make sure the new case lands under the correct `#if defined(MBEDTLS_<MODULE>_C)` guard and in the correct function (`mbedtls_high_level_strerr` vs `mbedtls_low_level_strerr`) — that's determined mechanically by which bits (`0xFF80` vs `~0xFF80`) the new code's numeric value occupies.

That last step — where the generator actually sources its list of `MBEDTLS_ERR_*` defines from, and the exact regen command — is the part I'm flagging as an honest gap rather than guessing at from training-data memory of mbedtls's public layout.
