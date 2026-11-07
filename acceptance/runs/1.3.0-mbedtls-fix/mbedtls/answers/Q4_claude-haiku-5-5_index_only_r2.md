The string is built in `library/error.c`, and the switch arms that map each code to text are generated, so a contributor adds the code in a header and regenerates rather than hand-editing `error.c`.

**Runtime path (answered from the index)**

```
caller: mbedtls_strerror(ret, buf, buflen)        library/error.c:792
  │  buflen == 0 → return
  │  zero buf; ret = -ret if negative
  ├─ ret & 0xFF80 (high-level part, module) ──► mbedtls_high_level_strerr(ret)   error.c:174
  │     e.g. "CIPHER - Bad input parameters"       (unknown → "UNKNOWN ERROR CODE (%04X)")
  │     if that module is SSL fatal alert → return, skip low-level part
  ├─ ret & ~0xFF80 (low-level part) ──────────► mbedtls_low_level_strerr(ret)    error.c:537
  │     e.g. "NET - Failed to open a socket"       (unknown → "UNKNOWN ERROR CODE (%04X)")
  └─ both present → join with " : " (only if ≥5 bytes remain), then append low-level text
```

- `mbedtls_strerror` returns `void`. It writes into the caller's buffer and always NUL-terminates it, truncating if needed.
- Each switch arm is wrapped in the module's `#if defined(MBEDTLS_xxx_C)`, so a module compiled out has no translation.
- The whole function is gated by `MBEDTLS_ERROR_C`. A second definition at `error.c:867` covers the `MBEDTLS_ERROR_STRERROR_DUMMY` case, which is used when `MBEDTLS_ERROR_C` is off.
- The two lookup functions are marked "Begin Auto-Generated Code" in `error.c`.

**Adding a new code**

1. Define the `MBEDTLS_ERR_<MODULE>_<NAME>` macro in the module's public header under `include/mbedtls/`. The index shows these as plain `#define`s with negative values, e.g. `MBEDTLS_ERR_ENTROPY_NO_SOURCES_DEFINED` is `-0x0040` in `entropy.h:43`. It must fall in the correct band: high-level bits for the module, low bits for the sub-code.
2. Add the description text to the generator's input. `scripts/generate_errors.pl` takes `include_dir data_dir error_file` (or no arguments) and writes `error.c`. The index cannot show where the description strings live. The data files are not indexed, so check the script source and its data directory before editing.
3. Regenerate `library/error.c` with `scripts/generate_errors.pl` through the project's normal entry point rather than by hand. Do not edit the generated arms directly.
4. Commit the header, the data, and the regenerated `error.c` together. `tests/scripts/check-generated-files.sh` checks that generated files are up to date, so a hand-edited or stale `error.c` should fail that check.
5. Run the gate through pre-commit, per `AGENTS.md`. Because `error.c` changes, the `mbedtls_strerror` body changes are not affected, but if you touch any function body, bump its `@version`.

**What I could not confirm from the index**

- The generator's internals and the exact invocation, since `generate_errors.pl` has no indexed symbols beyond its file doc.
- Where the description strings are stored.
- Whether adding a brand-new module needs extra registration beyond a new `#if` block.

Reading `scripts/generate_errors.pl` and its data directory directly would settle those three points.