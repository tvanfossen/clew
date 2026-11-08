The path from a negative return code to a string runs through `mbedtls_strerror()` in `library/error.c`. That file is generated, and the generator is what a contributor edits.

**Runtime path**

```
caller: ret = mbedtls_xxx(...)            # e.g. -0x0020
  └─ mbedtls_strerror(ret, buf, buflen)   library/error.c
       ├─ buflen==0 → return; zero buf; ret = -ret → 0x0020
       ├─ high = ret & 0xFF80              (module-class bits)
       │    └─ mbedtls_high_level_strerr(ret) → "SSL - ..." etc.
       │       (switch on case -(MBEDTLS_ERR_X) over the high-level modules)
       │    └─ if SSL fatal alert: return early (don't decode the low part)
       ├─ low = ret & ~0xFF80
       │    └─ if low == 0: return
       │    └─ append " : " if high text exists
       │    └─ mbedtls_low_level_strerr(ret) → "AES - Invalid key length"
       └─ NULL from either lookup → "UNKNOWN ERROR CODE (%04X)"
```

The masks come from the bit layout documented in `include/mbedtls/error.h`: a sign bit, three high-level module bits, five module-specific bits, and seven low-level bits. So one code can carry two strings. For example, `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` (`-0x7780`) yields only its high-level text, and a code combining an SSL error with a low-level error yields `"SSL - … : AES - …"`.

Each lookup is a `switch` whose cases are `case -(MBEDTLS_ERR_NAME):` followed by `return "MODULE - description";`. The `MODULE` prefix comes from the macro name, and the description comes from the Doxygen comment next to the `#define`.

**How the table is generated**

`library/error.c` is checked in, but it is produced by `scripts/generate_errors.pl` from two inputs:

1. `include/mbedtls/*.h` — the generator scans every header with a regex for `#define MBEDTLS_ERR_xxx -0xNNNN` and its doc comment.
2. `scripts/data_files/error.fmt` — the template with `HEADER_INCLUDED`, `LOW_LEVEL_CODE_CHECKS`, and `HIGH_LEVEL_CODE_CHECKS` placeholders.

Regeneration is wired in: `library/Makefile` (rule for `error.c`, triggered by header changes), `library/CMakeLists.txt`, and `scripts/make_generated_files.bat`. `tests/scripts/check-generated-files.sh` runs the generator and fails if the committed `library/error.c` differs.

**What a contributor has to do to add one**

1. **Define the code in the right module header** (e.g. `include/mbedtls/aes.h`) as `#define MBEDTLS_ERR_<MODULE>_<NAME> -0xNNNN`. The value must fit the layout and not collide. The generator dies on a duplicate value.
2. **Attach exactly one doc comment**, either before (`/** ... */`) or after (`/*!< ... */`) the define. Neither or both is a hard generator error. The text becomes the human-readable description, so write it as a short phrase without a trailing period. Don't use `\name` in the before-comment; the generator discards that comment.
3. **Use a module the generator knows.** The prefix must be in `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`, or it exits with "Do not know how to handle". A brand-new module also needs its `#include` and `#if` guard mapping in the script, and the header must be listed in the script's include handling. Otherwise it aborts with "has not been included".
4. **Regenerate and commit `library/error.c`** via `.venv/bin/pre-commit`/the make target, not by hand. Hand-editing it fails `check-generated-files.sh`.
5. **Add a case to `tests/suites/test_suite_error.data`** (`error_strerror:-0x....:"MODULE - text"`) so the string is pinned. I'm inferring this from the existing entries; the test suite itself is what checks the output.

Caveat: I read the generator and runtime code but did not build or run the generator or the test suite in this checkout, so the exact failure behaviour above is from reading the Perl, not from a run.