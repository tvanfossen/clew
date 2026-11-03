**How a negative code becomes a string**

1. The caller passes the negative `ret`, a buffer, and its length to `mbedtls_strerror` (`library/error.c:792`, declared in `include/mbedtls/error.h:165`). It returns nothing: it writes into the buffer, truncating if needed, and always null-terminates. A zero-length buffer returns immediately.
2. The function negates `ret` and splits it by bit mask. The high-level part is `ret & 0xFF80`, which names the module (e.g. CIPHER). It goes to `mbedtls_high_level_strerr` (`error.c:174`), a `switch` over the module-level codes. A miss yields `UNKNOWN ERROR CODE (%04X)`.
3. If the high-level part is the SSL fatal-alert code, the function returns there and does not translate the low-level part.
4. The low-level part is `ret & ~0xFF80`. If it is zero, the high-level text stands alone. Otherwise, if the buffer already holds high-level text, it appends `" : "` (only when at least 5 bytes remain). Then `mbedtls_low_level_strerr` (`error.c:537`) switches over the specific codes, with the same `UNKNOWN` fallback.

So `-0x0010`-style codes come out as a module string, a specific string, or the joined form `HIGH : LOW`, e.g. `CIPHER - Authentication failed (for AEAD modes)`.

`library/error.c` contains a second `mbedtls_strerror` candidate at line 867, which the index reports as gated by `MBEDTLS_ERROR_C` and `MBEDTLS_ERROR_STRERROR_DUMMY`. I could not confirm from the index which branch that is. The `switch` blocks are wrapped in `#if defined(MBEDTLS_<MODULE>_C)`, so codes from a module compiled out fall through to `UNKNOWN`.

**Where the table comes from**

`library/error.c` is not hand-maintained. `library/CMakeLists.txt:134` has a custom command that runs `scripts/generate_errors.pl` over `include/mbedtls` and `scripts/data_files`, using `scripts/data_files/error.fmt`, and writes `error.c` into the build directory. The generator's file doc gives its usage. Its body, the `.fmt` template and the CMake `error_headers` list are not in the index, so I cannot say exactly which headers it scans or where the description strings are read from.

**To add a new code**

- Add the `MBEDTLS_ERR_<MODULE>_<NAME>` define with its negative value in the module's public header, following the pattern of the `MBEDTLS_ERR_ERROR_*` defines in `error.h`. The index shows that pattern but not the per-module header convention, so check it in a neighbouring module.
- Do not edit `library/error.c`. The build regenerates it. Make sure the generator picks up your define and its description. Check `generate_errors.pl` and `data_files/` for the description source, because the index does not show it.
- Keep the value inside the mask scheme: module bits in `0xFF80`, specific bits below. This is inferred from the masks, not stated in the index.
- Verify with `programs/util/strerror` (accepts decimal or `-0x` hex, per its `USAGE` string). Note that `BRANCHES.md` treats a newly documented error condition as a compatibility-relevant change, so it should be recorded in the changelog.