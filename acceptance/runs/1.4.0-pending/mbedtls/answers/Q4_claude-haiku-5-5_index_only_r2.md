**Short answer:** `mbedtls_strerror()` splits the negative code into a high-level module part and a low-level part, looks each up in a switch statement, and joins the two strings. That switch is generated at build time by `scripts/generate_errors.pl`, so a contributor adds a code by declaring it in a public header and rebuilding, not by editing `error.c`.

**Runtime path (`library/error.c`)**

```
caller: int ret = mbedtls_xxx(...)   // ret < 0
  │
  ▼
mbedtls_strerror(ret, buf, buflen)            error.c:792
  ├─ buflen == 0 → return; else memset(buf, 0)
  ├─ ret = -ret                                // undo the sign
  ├─ high = ret & 0xFF80
  │    └─ mbedtls_high_level_strerr(ret)       error.c:174  (switch, "CIPHER - …", "DHM - …")
  │         NULL → "UNKNOWN ERROR CODE (%04X)"
  │    └─ if high == SSL fatal alert → return  (skip the low-level part)
  ├─ low = ret & ~0xFF80; if 0 → return
  ├─ if buf already has text → append " : "
  └─ mbedtls_low_level_strerr(ret)             error.c:537  (switch, "AES - Invalid key length", …)
       NULL → "UNKNOWN ERROR CODE (%04X)"
```

- The sign is removed first because the switch cases are written as `-(MBEDTLS_ERR_…)`.
- The high and low halves are separate lookups. A code can have both, and the result is one string such as `"X - high : Y - low"`.
- Every module block sits behind its `#if defined(MBEDTLS_<MODULE>_C)`, so a module that is compiled out contributes no strings.
- The output is always null-terminated and truncated to `buflen`. An unknown code is reported as `UNKNOWN ERROR CODE (xxxx)`, not as an empty string.
- `programs/util/strerror.c` wraps this function for the shell, so you can check a code from the command line.

**How `error.c` gets generated**

- `library/CMakeLists.txt:134` runs `generate_errors.pl` as a custom command. It takes `include/mbedtls` and `scripts/data_files` as inputs and writes `${CMAKE_CURRENT_BINARY_DIR}/error.c`. So `error.c` lives in the build tree, not the source tree.
- The rule's dependencies are `generate_errors.pl`, the `error_headers` list, and `scripts/data_files/error.fmt`. Changing a header therefore triggers regeneration.
- The script's own usage line is `generate_errors.pl include_dir data_dir error_file`.

**What a contributor does to add a new code**

1. Add a `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` in that module's public header, using the module's existing band and value range. The generator scans the headers listed in `error_headers`, so a code outside those headers is never seen.
2. Give it a description the generator can use. The index does not show where that text comes from; the most likely source is the header's doc comment, but I have not verified it.
3. Rebuild through the normal CMake build. `error.c` is regenerated and the new case appears in the right module block.
4. Do not hand-edit `error.c`. The next build overwrites it.
5. Confirm with `programs/util/strerror <code>`, and add a test that asserts the new string. The repo's conventions say tests are specifications, so a test that checks the exact text is the right form.

**Gaps in what I could see**

- `scripts/generate_errors.pl` has no indexed symbols, and `error.fmt` is not indexed at all. I could not confirm the exact header-scanning rule, the description source, or the format template. Read those two files before relying on step 2.
- `mbedtls_strerror` appears twice in the index (`error.c:792` and `:867`). I assume the second is the variant used when `MBEDTLS_ERROR_STRERROR_DUMMY` is set, but I did not verify that. The 792 body is the one that does the work.
- I did not check `ChangeLog.d` or any docs for an additional convention a contributor might need to follow.