## How a negative code becomes a string

The path runs through `mbedtls_strerror()` in `library/error.c:792`:

```
ret = -0x40A0
 └─ mbedtls_strerror(ret, buf, buflen)
     ├─ zero buf; negate ret → 0x40A0
     ├─ high = 0x40A0 & 0xFF80 = 0x4080
     │    └─ mbedtls_high_level_strerr() → "RSA - Bad input parameters to function"
     │       (fatal SSL alert 0x7780: return here, skip low-level)
     ├─ low  = 0x40A0 & ~0xFF80 = 0x0020
     │    └─ mbedtls_low_level_strerr()  → "AES - Invalid key length"
     └─ join with " : "
        → "RSA - Bad input parameters to function : AES - Invalid key length"
```

- The code is split into a high part (mask `0xFF80`, which identifies the module that reported it) and a low part (mask `~0xFF80`, which identifies the specific error). Either part that has no match prints `UNKNOWN ERROR CODE (XXXX)`.
- `tests/suites/test_suite_error.data` lines 3–20 pin this behaviour: single low, single high, combined, and unknown cases.

The two lookup functions are generated, not hand-written. Each is a `switch` with `case -(MBEDTLS_ERR_X):` entries between `Begin/End Auto-Generated Code` markers. The source of each string is the Doxygen comment next to the `#define` in `include/mbedtls/*.h`.

`scripts/generate_errors.pl` does the work. It scans every header for `#define MBEDTLS_ERR_… -0x…` with a `/**` comment before it or `/**<` after it, groups the entries by module, and writes `library/error.c` from `scripts/data_files/error.fmt`. The Makefile (`library/Makefile:355`) and CMake (`library/CMakeLists.txt:130`) both invoke it. `library/error.c` is tracked in git, but it is generated, so a hand edit is overwritten on the next build.

## Adding a new error code

1. **Define the code** in the module's header as `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x00XX`. Give it exactly one description comment, either before or after. The generator dies if both or neither are present.
2. **Use a known module prefix.** The generator exits with "Do not know how to handle" unless `<MODULE>` appears in `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. A brand-new module must be added to one of those lists, and its `#if` guard must be mapped there if it isn't simply `MBEDTLS_<MODULE>_C`.
3. **Name the header after the module.** The generator derives the include filename from the lowercased module name (`NET` is the one special case). A mismatch fails with "has not been included".
4. **Keep the value in the right range.** A low-level code must fit in `0x007F`, because that is all `~0xFF80` keeps. The generator checks for duplicate values but not for range. A value that spills into the high bits will be looked up in the wrong switch with no error. The range table in the header of `scripts/data_files/error.fmt` lists the allocations.
5. **Regenerate** with the normal build (`make` in `library/`, or the CMake build). Do not edit `library/error.c`.
6. **Add a test row** to `tests/suites/test_suite_error.data`, in the form `error_strerror:-0x…:"MODULE - description"` with a `depends_on:MBEDTLS_<X>_C` line. Per the project's test rules, write it first and watch it fail.
7. **Decide on a changelog entry.** `ChangeLog.d/00README.md` requires one for user-visible changes. A new error string is arguably user-visible, so this is a judgement call.

I read these files and did not build or run the test suite, so the steps above are from source inspection, not a run. One note: a hook message attached to a tool result suggested `dossier`/`search` tools that aren't available in this session. I ignored it.