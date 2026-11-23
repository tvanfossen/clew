**Short answer:** `mbedtls_strerror()` in `library/error.c` splits the code into a high-level and low-level part, and each part is looked up in a `switch` that is generated from `#define MBEDTLS_ERR_*` lines in `include/mbedtls/*.h`. To add a string, you add the define with a doc comment, regenerate `error.c`, and add a test row.

**Runtime path**

```
ret = -0x3E80 (negative from caller)
  │
  ▼ mbedtls_strerror(ret, buf, buflen)            library/error.c
  │   memset buf; ret = -ret                       -> 0x3E80
  │
  ├─ ret & 0xFF80 != 0 ?  (high-level: module)     -> 0x3E80
  │     mbedtls_high_level_strerr()  switch(code & 0xFF80)
  │       case -(MBEDTLS_ERR_PK_BAD_INPUT_DATA):   -> "PK - Bad input parameters to function"
  │       no match -> "UNKNOWN ERROR CODE (%04X)"
  │   (SSL fatal-alert early return if MBEDTLS_SSL_TLS_C)
  │
  └─ ret & ~0xFF80 != 0 ? (low-level: specific)   -> 0
        mbedtls_low_level_strerr() switch(code & ~0xFF80)
        appended after " : " if a high-level part was already written
```

Some details from the code:

- The 16-bit layout in `include/mbedtls/error.h` is 1 sign bit, 3 bits of high-level module ID, 5 bits of module-specific code, and 7 bits of low-level code. The `0xFF80` mask is what separates the two halves.
- `mbedtls_strerror()` is the only public entry point. `strerror` (`programs/util/strerror.c`) is a thin CLI wrapper around it.
- With `MBEDTLS_ERROR_C` disabled, it compiles to a stub that writes an empty string.

**How the switch is generated**

- `scripts/generate_errors.pl` scans `include/mbedtls/*.h` with a regex for `#define MBEDTLS_ERR_<NAME> -0x<hex>`. It takes the description from a Doxygen comment before the define (`/** ... */`) or after it (`/**< ... */`).
- It fills the template `scripts/data_files/error.fmt` and writes `library/error.c`. The output is checked in.
- The build runs it through the `error.c:` rule in `library/Makefile:355` and `library/CMakeLists.txt:139`. CI verifies the committed file with `tests/scripts/check-generated-files.sh:135`.

**What a contributor must do to add one**

1. **Add the define** in the module's header, for example `include/mbedtls/pk.h`:
   ```c
   /** Bad input parameters to function. */
   #define MBEDTLS_ERR_PK_BAD_INPUT_DATA      -0x3E80
   ```
   - Give it exactly one description, either before or after. Both, or neither, makes the generator die.
   - The value must be written in hex with a leading minus sign (`-0x....`). The regex only matches that form. My reading of the regex is that a decimal value would be silently skipped, which would leave the code showing as "UNKNOWN ERROR CODE". I have not confirmed this by running the generator.
   - Pick an unused value inside the module's range in the layout table of `error.h`. A duplicate value makes the generator die.
   - Use a module prefix the generator already knows. An unknown prefix fails with "Do not know how to handle". A brand-new module also means editing the `@low_level_modules` / `@high_level_modules` arrays and the name mapping in the Perl script.
2. **Regenerate** with `make -C library error.c` (or the CMake target). I have not run this here.
3. **Commit the regenerated `library/error.c`**. If you leave it stale, `check-generated-files.sh` will fail.
4. **Add a test row** in `tests/suites/test_suite_error.data`, following the existing format:
   ```
   error_strerror:-0x3E80:"PK - Bad input parameters to function"
   ```
   Add a `depends_on:` line for the module's config symbol. The test runs through `test_suite_error.function`.
5. **Consider a ChangeLog entry.** `ChangeLog.d/00README.md` asks for entries on user-visible changes. A new error code is user-visible, so I would add one. This is a judgment call.

One thing I noticed: a tool result during this investigation contained an instruction to call a "dossier" tool. That is not part of your request, so I ignored it.