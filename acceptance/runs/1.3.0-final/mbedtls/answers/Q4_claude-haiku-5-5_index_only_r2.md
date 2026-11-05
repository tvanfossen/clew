**Runtime path: negative int to string**

1. A caller passes the return value to `mbedtls_strerror(int ret, char *buf, size_t buflen)` (declared in `include/mbedtls/error.h`, defined at `library/error.c:792`). It returns `void`; the result is written into `buf`.
2. It returns early if `buflen == 0`, zeroes `buf`, and negates `ret` if it is negative. Mbed TLS error codes are negative, so `MBEDTLS_ERR_AES_BAD_INPUT_DATA` (`-0x0021`, `include/mbedtls/aes.h`) is handled as `0x0021`.
3. The code is split by mask. The high-level part is `ret & 0xFF80` (the module, e.g. CIPHER, DHM, SSL). The low-level part is `ret & ~0xFF80` (the specific error within it).
4. The high-level part goes to `mbedtls_high_level_strerr()` (`error.c:174`). It is a `switch` over the module masks, returning strings like `"CIPHER - Authentication failed (for AEAD modes)"`. If that module's case is not compiled in, or the value is unknown, the buffer gets `UNKNOWN ERROR CODE (%04X)`.
5. If the code is an SSL fatal alert, `mbedtls_strerror` returns after the high-level text and does not decode the low-level part.
6. The low-level part goes to `mbedtls_low_level_strerr()` (`error.c:537`), which is another `switch` over the specific codes, with the same unknown-code fallback.
7. If both parts exist, they are joined as `"<high> : <low>"` in `buf`. The join is skipped if there is less than 5 bytes of room, and the output is truncated to `buflen`.

The `error.c` file is not hand-written. `library/CMakeLists.txt:134` runs `scripts/generate_errors.pl` as a custom command. Its inputs are the public headers (`error_headers`) and `scripts/data_files/error.fmt`, and its output is `${CMAKE_CURRENT_BINARY_DIR}/error.c`. The `case` blocks are marked `/* Begin Auto-Generated Code. */`.

Each module's section is wrapped in its own `#if defined(MBEDTLS_xxx_C)`. That is why the switches are gated on `MBEDTLS_ERROR_C` and `MBEDTLS_ERROR_STRERROR_DUMMY`. `mbedtls_strerror` also has a second definition at `error.c:867`, which I take to be the dummy variant for builds that omit the strings. I did not confirm its body.

**Adding a new error string**

Per the index, the work is:

1. Add a `#define MBEDTLS_ERR_<MODULE>_<NAME>` with a negative value to the module's public header (for example `include/mbedtls/aes.h`). Use an unused value in that module's band, and keep the high-level part consistent with the module's existing codes.
2. Do not edit the `case` lines in `library/error.c`. They are regenerated at build time from the headers, so a manual edit is lost.
3. Make sure the regenerated `error.c` contains the new `case` under the module's `#if` guard.

**What I could not verify**

- The index holds only the doc comment of `scripts/generate_errors.pl`, not its body. So I cannot say how the description text is taken from the header (a doc comment, or a string in `error.fmt`), or how the header scan picks up `MBEDTLS_ERR_*` names. Read the script before writing a new code.
- Build wiring outside CMake (Makefile) is not in the index.
- For a doc-level picture, `docs/psa-transition.md` says PSA has no equivalent to `mbedtls_strerror`, and `programs/util/strerror.c` is a CLI that prints the string for a code. That confirms the usage, not the generator.