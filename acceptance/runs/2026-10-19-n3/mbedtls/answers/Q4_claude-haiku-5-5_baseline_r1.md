## From return code to string

The caller passes the negative return value to `mbedtls_strerror(ret, buf, buflen)` (declared in `include/mbedtls/error.h:165`, defined in `library/error.c`). It does the following:

```
ret (e.g. -0x6A80)
  │  ret = -ret                          → 0x6A80
  ├─ high = ret & 0xFF80                 → 0x6A80  → mbedtls_high_level_strerr()
  │     switch(high): case -(MBEDTLS_ERR_SSL_...): return "SSL - ..."
  │     (SSL fatal alert? → return now, skip low level)
  ├─ low  = ret & ~0xFF80                → 0x0000  (zero → done)
  │     mbedtls_low_level_strerr()
  │     switch(low): case -(MBEDTLS_ERR_...): return "MODULE - description"
  └─ buf = "<high> : <low>"  (or "UNKNOWN ERROR CODE (XXXX)" on a miss)
```

Details:

- **Sign and split.** It negates the value, then masks it. Bits in `0xFF80` select a high-level module (CIPHER, PK, SSL, X509, and so on). The remaining bits select a low-level module (AES, MD, BIGNUM, and so on). A single code can contribute to both strings.
- **Lookup.** Both `mbedtls_*_strerr` functions are `switch` statements over `case -(MBEDTLS_ERR_X):` labels. Each label returns a string of the form `"MODULE - description"`.
- **Composition.** The high-level text goes into `buf` first, then `" : "`, then the low-level text. Unknown codes produce `UNKNOWN ERROR CODE (%04X)`.
- **Generated file.** `library/error.c` is generated, not hand-written. Its header comment says so, and `scripts/generate_errors.pl` writes the `switch` bodies and `#include`s into it from `scripts/data_files/error.fmt`.

## Adding a new error string

1. **Define the code** in the module's public header, e.g. `include/mbedtls/<module>.h`, as `#define MBEDTLS_ERR_<MODULE>_<NAME> -0xNNNN`. Attach exactly one Doxygen description, either a `/** ... */` block before it or a `/**< ... */` after it. Having both, or neither, makes the generator die.
2. **Use a module the generator knows.** The module name comes from the prefix. `scripts/generate_errors.pl` has hard-coded lists of low-level and high-level modules, plus special cases (`MPI`→`BIGNUM`, `NET`→`net_sockets.h`, and so on). A new module must be added to those lists, or the script exits with "Do not know how to handle".
3. **Keep the value unique and in the right range.** The generator rejects duplicate values. The range table in `include/mbedtls/error.h` (around lines 60–95) says where each module's codes live.
4. **Regenerate; don't hand-edit.** Run `perl scripts/generate_errors.pl` from the repo root, or build via `library/Makefile` / CMake, which rerun it. `tests/scripts/check-generated-files.sh` fails CI if `library/error.c` is stale.
5. **Add a changelog entry** in `ChangeLog.d/` if the change is user-visible, per `ChangeLog.d/00README.md`. A new error code usually qualifies.

I read the generator and `error.c` but didn't run the generator or the check script, so the exact failure messages above come from reading the code.