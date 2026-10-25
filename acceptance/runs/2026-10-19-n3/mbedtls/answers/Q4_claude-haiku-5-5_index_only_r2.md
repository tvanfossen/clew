The runtime path is clear from the index. The contributor path is only partly visible, because the generator for the table isn't in the index.

**How a negative code becomes a string**

```
caller: ret = mbedtls_xxx(...)   // e.g. -0x0021
   │
   ▼
mbedtls_strerror(ret, buf, buflen)            library/error.c:792
   ├─ buflen == 0 → return; else memset(buf, 0)
   ├─ ret = -ret                                // sign stripped
   ├─ high = ret & 0xFF80
   │    └─ mbedtls_high_level_strerr(ret)      error.c:174  (module, e.g. "CIPHER - ...")
   │         └─ if SSL fatal alert → return early (no low-level part)
   ├─ low = ret & ~0xFF80
   │    └─ mbedtls_low_level_strerr(ret)       error.c:537  (specific cause, e.g. "AES - Invalid input data")
   └─ join with " : " if both present; "UNKNOWN ERROR CODE (%04X)" on a miss
```

1. The caller passes the negative int and a buffer to `mbedtls_strerror` (declared in `include/mbedtls/error.h`, defined in `library/error.c:792`). It always NUL-terminates and truncates if needed.
2. The sign is stripped, then the value is split on the `0xFF80` mask. The high bits identify the module (`MBEDTLS_ERR_AES_*`, `MBEDTLS_ERR_SSL_*`, and so on); the low bits identify the specific error.
3. Each half is looked up by `mbedtls_high_level_strerr` or `mbedtls_low_level_strerr`. Each is a large `switch` over the `MBEDTLS_ERR_*` constants, and every case is wrapped in `#if defined(MBEDTLS_<MODULE>_C)`. Unknown codes fall back to `UNKNOWN ERROR CODE (xxxx)`.
4. The two halves are joined with ` : `. The whole file is gated by `MBEDTLS_ERROR_C`, and by `MBEDTLS_ERROR_STRERROR_DUMMY` in some configs.

Example: `MBEDTLS_ERR_AES_BAD_INPUT_DATA` is `-0x0021` (`include/mbedtls/aes.h`). That maps to the low-level case `"AES - Invalid input data"`.

**What a contributor has to do to add one**

The index confirms these parts:
- Define the new `MBEDTLS_ERR_<MODULE>_<NAME>` macro with a negative value in the module's public header, for example `include/mbedtls/aes.h`. The new value has to fall in the module's high-level or low-level range.
- Add a matching `case -(MBEDTLS_ERR_...)` with its description string in the right `#if defined(MBEDTLS_<MODULE>_C)` block of `mbedtls_high_level_strerr` or `mbedtls_low_level_strerr` in `library/error.c`. Keep the description in the `"MODULE - text"` style used by the other cases.

The index does not confirm this part: the switch bodies are marked `/* Begin Auto-Generated Code. */`, which means they are produced by a generator rather than written by hand. The index holds no generator script. `scripts/` has 21 indexed files and none of them is an error-table generator, and a prose search for `generate_errors` returns nothing. The index can't tell me the generator's name, what it reads, or how to re-run it. The fix is to find the generator in the repository (or its docs) and regenerate `error.c` instead of hand-editing the generated block. I did not verify that from the index.

I also could not check whether a test or doc requires new codes to be documented. The index shows no requirement or covering-test links on these functions. The repo's `ChangeLog.d/` directory is indexed, but I did not inspect its contents.