**From code to string**

1. **Codes are negative macros in module headers.** Each module defines `MBEDTLS_ERR_<MODULE>_<NAME>` as a negative hex value. For example, `MBEDTLS_ERR_AES_INVALID_KEY_LENGTH` is `-0x0020` in `include/mbedtls/aes.h:44`.

2. **The caller invokes `mbedtls_strerror(ret, buf, buflen)`.** It is declared in `include/mbedtls/error.h:165` and defined at `library/error.c:792`. The index shows only the `error.c` definition and its body, not the header's documentation for the parameters.

3. **`mbedtls_strerror` splits the code.** It returns early if `buflen` is 0, clears the buffer, and negates a negative `ret`. It then splits the value with two masks:
   - High-level part (`ret & 0xFF80`): the module identity. It is passed to `mbedtls_high_level_strerr`.
   - Low-level part (`ret & ~0xFF80`): the specific error. It is passed to `mbedtls_low_level_strerr`.

4. **Each lookup is a switch.** `mbedtls_high_level_strerr` (`error.c:174`) and `mbedtls_low_level_strerr` (`error.c:537`) return a fixed string per code, such as `"AES - Invalid key length"`. Each module's cases sit inside `#if defined(MBEDTLS_<MODULE>_C)` guards, so a module disabled in the build contributes no cases.

5. **Output is assembled into the buffer.**
   - An SSL fatal alert message returns after the high-level text, skipping the low-level lookup.
   - If both parts are present, they are joined with `" : "`, provided there is room.
   - An unknown code becomes `UNKNOWN ERROR CODE (%04X)`.
   - Output is always null-terminated, because every write goes through `mbedtls_snprintf`.

6. **Gating.** The function is compiled under `MBEDTLS_ERROR_C`. When that is off, the stub gated by `MBEDTLS_ERROR_STRERROR_DUMMY` (around `error.c:867`) is used, per `include/mbedtls/mbedtls_config.h:1170`. I inferred the stub's exact line from the gate ranges.

```
caller ── mbedtls_strerror(ret, buf, len)
            │ negate, memset
            ├─ ret & 0xFF80  → mbedtls_high_level_strerr → "MODULE - text"
            │      (SSL fatal alert? stop here)
            ├─ ret & ~0xFF80 → mbedtls_low_level_strerr  → "MODULE - text"
            └─ join with " : ", or UNKNOWN ERROR CODE (%04X)
```

**Where the switch tables come from.** `library/error.c` is not hand-written. `library/CMakeLists.txt:134` runs `scripts/generate_errors.pl` at build time. Its inputs are the `include/mbedtls` headers and `scripts/data_files/error.fmt`, and the output is written to the build directory. The index can't see inside the Perl script or `error.fmt`, so the rules below are inferred from the generated output, not verified.

**Adding a new code**

1. Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` in the owning module's header under `include/mbedtls/`. Use an unused value in that module's range. I did not verify the range convention.
2. Give it a description comment in the header. The generated text looks like `"<MODULE> - <description>"`, so the description probably comes from that comment. I did not verify this.
3. Do not edit `error.c`. Rebuild through the CMake target so the generator reruns. The generator depends on the headers, so the new case appears under the module's `#if` guard.
4. If the code should map to a PSA error, update the translation function. `mbedtls_to_psa_error` already references existing codes, so it is a likely place, but I did not check it.
5. Check the repo's convention for changelog entries (there is a `ChangeLog.d/` directory). I did not check this.