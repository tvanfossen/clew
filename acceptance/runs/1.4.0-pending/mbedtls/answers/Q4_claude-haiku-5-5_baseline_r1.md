## How a negative code becomes a string

The path is `mbedtls_strerror()` in `library/error.c`, which is generated, not hand-written.

```
caller: ret = mbedtls_xxx(...)  (ret < 0)
   │
   ▼
mbedtls_strerror(ret, buf, buflen)           library/error.c:792
   ├─ zero buf; ret = -ret
   ├─ if (ret & 0xFF80): high = mbedtls_high_level_strerr(ret)
   │      switch on (ret & 0xFF80)  → "MODULE - description" or NULL
   │      if NULL → "UNKNOWN ERROR CODE (XXXX)"
   │      if SSL FATAL_ALERT → return (skip low-level)
   ├─ low = ret & ~0xFF80; if 0 → return
   ├─ if high present → append " : "
   └─ low = mbedtls_low_level_strerr(ret)
          switch on (ret & ~0xFF80) → "MODULE - description" or NULL
          if NULL → "UNKNOWN ERROR CODE (XXXX)"
```

The mask `0xFF80` splits a code into a high-level part (the module bits) and a low-level part (the bits under 0x80). So `-0x40A0` decodes as RSA (`0x4080`) plus AES (`0x20`), and the output is `RSA - Bad input parameters to function : AES - Invalid key length`. That exact string is pinned in `tests/suites/test_suite_error.data`.

Where `error.c` comes from:

- `include/mbedtls/*.h` contains `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x00XX`, with a Doxygen description either before (`/** */`) or after (`/**< */`).
- `scripts/generate_errors.pl` scans those headers and fills the `HEADER_INCLUDED`, `LOW_LEVEL_CODE_CHECKS` and `HIGH_LEVEL_CODE_CHECKS` placeholders in `scripts/data_files/error.fmt`.
- It writes `library/error.c`. The Makefile rule is at `library/Makefile:355-360`, and the CMake custom command is at `library/CMakeLists.txt:136-144`.
- `library/error.c` is tracked in git, so the regenerated file is committed too.

## Adding a new code

1. **Define it in the module's header** in `include/mbedtls/`, with one Doxygen description, before or after, not both. The script dies on a missing description, on both, and on a duplicate value.
2. **Name the module so the script recognises it.** The token after `MBEDTLS_ERR_` must be in the `@low_level_modules` or `@high_level_modules` list in `generate_errors.pl`, or the script exits with "Do not know how to handle". A new module also needs its header name to match the lowercased module name (`NET` is the one special case), or the script reports "has not been included".
3. **Pick an unused value.** I did not confirm that a checker enforces that low-level modules stay in the low bits and high-level modules in the high bits. The runtime does split on `0xFF80`, so a code placed in the wrong range would be looked up in the wrong table and come back as `UNKNOWN ERROR CODE`.
4. **Add a test row first** in `tests/suites/test_suite_error.data`, using `depends_on:` for the module's `MBEDTLS_*_C` guard and the expected string. Run it red, then make it green. The generator wraps each module's entries in `#if defined(MBEDTLS_<MODULE>_C)`, so the `depends_on` must match that guard.
5. **Regenerate and commit `library/error.c`** by building, so the Makefile or CMake rule runs. The repo's gate is `.venv/bin/pre-commit run --all-files`, which the project requires instead of running tools directly.

I did not check whether the repo also expects a ChangeLog entry for new error codes.