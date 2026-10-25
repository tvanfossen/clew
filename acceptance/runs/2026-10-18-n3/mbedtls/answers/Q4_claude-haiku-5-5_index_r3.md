A negative code like `-0x40A0` becomes text in one function, `mbedtls_strerror()` in `library/error.c`, which calls two generated lookup functions. The lookup tables are generated from the header `#define`s, so a contributor adds a string by adding a documented `#define` and regenerating, not by editing the table.

**Runtime path**

```
caller: ret = -0x40A0
   │
   ▼
mbedtls_strerror(ret, buf, buflen)        library/error.c:792
   │  buflen==0 → return; memset(buf,0)
   │  ret = -ret                          (sign dropped)
   │
   ├─ high = ret & 0xFF80 ──► mbedtls_high_level_strerr(ret)   error.c:174
   │     hit  → buf = "RSA - Bad input parameters to function"
   │     miss → buf = "UNKNOWN ERROR CODE (XXXX)"
   │     if high == -(MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE): return early
   │
   ├─ low = ret & ~0xFF80
   │     low == 0 → return (high-only code)
   │     else: if buf already has text, append " : "
   │           buf += "AES - Invalid key length" via mbedtls_low_level_strerr(ret)  error.c:537
   │
   ▼
buf = "RSA - Bad input parameters to function : AES - Invalid key length"
```

Each code is split into a high-level part (bits 7–15, the module that owns the error, such as RSA) and a low-level part (bits 0–6, a sub-code inside a lower module, such as AES). Both lookups are `switch` statements over `case -(MBEDTLS_ERR_X):`, and each returns the literal `"MODULE - description"`. Anything not found falls through to `NULL`, which `mbedtls_strerror` turns into `UNKNOWN ERROR CODE (%04X)`. The output is always NUL-terminated and truncated to `buflen`.

**Where the tables come from**

The `switch` bodies sit between `/* Begin Auto-Generated Code. */` markers and are not hand-written. The generator is `scripts/generate_errors.pl`, with template `scripts/data_files/error.fmt`. It:

1. Scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_xxx -0xNNNN` and takes the description from a doxygen comment.
2. Assigns each code to the low-level or high-level table by module name.
3. Writes `library/error.c` from the template.

**What a contributor has to do to add one**

1. **Define the code** in the module's header (for example `include/mbedtls/md.h`) as `#define MBEDTLS_ERR_MD_FOO -0xNNNN`. Add exactly one description, either a `/** ... */` block before it or a `/*!< ... */` after it. Having both, or neither, makes the generator die. The value must be unique across all headers, because the generator aborts on duplicates.
2. **New module only:** add its name to the `@low_level_modules` or `@high_level_modules` list in `scripts/generate_errors.pl`. Otherwise it fails with "Do not know how to handle". If the header file name does not match the lowercased module name, add a special case as is done for `NET` → `net_sockets.h`.
3. **Regenerate** with `perl scripts/generate_errors.pl` from the repo root, or through the `error.c` make rule. Do not hand-edit `library/error.c`. CI's `tests/scripts/check-generated-files.sh` regenerates it and fails on any diff.
4. **Add a test case** to `tests/suites/test_suite_error.data`, using the existing format:
   ```
   My new error
   depends_on:MBEDTLS_FOO_C
   error_strerror:-0xNNNN:"FOO - Description"
   ```
   The test asserts the exact string.
5. **Changelog:** `ChangeLog.d/` exists with a `00README.md`. I did not read it, so check its convention before adding an entry.

I read these from source and did not run the generator or the test suite, so the regeneration and test steps are unverified here.