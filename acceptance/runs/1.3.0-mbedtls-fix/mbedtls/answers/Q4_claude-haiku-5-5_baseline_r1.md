The string comes from two layers: a generated lookup table in `library/error.c`, and a runtime decoder, `mbedtls_strerror()`, that splits the code into a high-level and a low-level part. Adding a new one means adding a documented `#define` to a public header and regenerating `error.c`. I didn't build or run anything; this is from reading the code.

**Runtime path (`library/error.c`, `mbedtls_strerror`, ~line 792)**

1. The buffer is zeroed, and the sign is dropped (`ret = -ret`), since codes are stored as negatives.
2. The high-level part is `ret & 0xFF80`. It goes to `mbedtls_high_level_strerr()`, which switches on that masked value and returns the module description (e.g. "AES", "SSL"), or `UNKNOWN ERROR CODE (XXXX)` if nothing matches.
3. If the code is an `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, it returns early and does not decode the low bits.
4. The low-level part is `ret & ~0xFF80`. If non-zero, it is appended after `" : "` with `mbedtls_low_level_strerr()`, which switches on the specific code.
5. If both parts are zero, the buffer holds only the high-level text, or stays empty for a plain 0.

The result looks like `"AES - Invalid key length"`, or `"X509 - ... : ASN1 - ..."` for a combined code. With `MBEDTLS_ERROR_C` off, a dummy version returns an empty string.

**Generation path (`scripts/generate_errors.pl`)**

`library/error.c` is not hand-written. The script:

1. Reads every `include/mbedtls/*.h` and matches this pattern: an optional `/** ... */` or `/*!` comment before, then `#define MBEDTLS_ERR_xxx  -0xNNNN`, then an optional `/**<` comment after. The description is the before-comment or the after-comment, not both. Missing or doubled descriptions are fatal.
2. Derives the module from the name prefix (`MBEDTLS_ERR_AES_*` → `AES`), with fixes for `MPI`→`BIGNUM`, `CTR`→`CTR_DRBG`, `HMAC`→`HMAC_DRBG`.
3. Rejects a module that is in neither `@low_level_modules` nor `@high_level_modules` (exit 1). A new module has to be added to one of those lists.
4. Rejects duplicate codes.
5. Emits `case -(MBEDTLS_ERR_X):  return "MODULE - description";` into the low-level or high-level switch, wrapped in `#if defined(MBEDTLS_<MOD>_C)` guards, plus `#include "mbedtls/<module>.h"` for each header it used.
6. Fills the template `scripts/data_files/error.fmt`.

**What a contributor has to do**

1. Add the code to the right header, e.g. `include/mbedtls/aes.h`. Pick an unused value in the module's range and write a Doxygen comment, either `/**< ... */` after the define or `/** ... */` before it. The text becomes the message.
2. If the code belongs to a module not already listed in the script, add that module to `@low_level_modules` or `@high_level_modules`. Then give it a fixed mapping if its name doesn't match its header name.
3. Regenerate: `cd library && make` (the Makefile rule at `library/Makefile:355` runs the script when `error.c` is stale), or the CMake rule in `library/CMakeLists.txt:139`. Don't edit `error.c` by hand.
4. Check that the generated file is up to date. `tests/scripts/check-generated-files.sh:135` regenerates it and diffs against the checked-in copy.
5. Run the tests through pre-commit, per `AGENTS.md`. Add a case to `tests/suites/test_suite_error.function` and its `.data` file so the new string is checked, and per the repo's TDD rule, see it fail first.

Note that `scripts/bump_version.sh` also references the generator, so a version bump touches it too.