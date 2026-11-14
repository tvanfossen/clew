**What it does.** `MBEDTLS_PRIVATE(member)` is a rename macro, defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Every public struct declares its fields through this macro (about 890 occurrences across 74 headers, e.g. `ssl.h`, `x509_crt.h`, `psa/crypto_struct.h`). In a default build, a field `flags` is really named `private_flags`. Code that writes `ctx->flags` fails to compile. The layout is unchanged; only the name moves.

**Who it's for.** The primary audience is external users. The rename is meant to make field access a compile error, so the layout can change in a minor release without breaking callers. The migration guide (`docs/3.0-migration-guide.md:62-74`) says to use accessors first. As a last resort, `bar.MBEDTLS_PRIVATE(foo)` still works in a default build, because the same macro expands at the use site to `private_foo`. The guide says that code "is likely to break in a future minor version."

**Where the opt-out is turned on in this tree.** Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` makes the macro the identity, so bare `ctx->flags` compiles. It is set in three places:

| Location | Scope |
|---|---|
| `library/common.h:132` | Every library `.c` that includes `common.h` first (e.g. `rsa.c:26`, `md.c`, `cmac.c`, `des.c`, `aria.c`, `psa_util.c`). This is the library's internal opt-out. |
| `programs/ssl/ssl_server2.c:8` | That one program only, defined before any include. |
| `programs/ssl/ssl_client2.c:8` | That one program only, defined before any include. |

**What that means for those files.**
- They are treated as internal to the library. They can use field names directly, and the compiler cannot flag them if a minor release changes a field.
- The layout is identical in both modes, so no ABI difference results. Only the names differ. The opt-out does not change the struct itself.
- It is a per-translation-unit switch. The `#ifndef` in `private_access.h` is evaluated the first time that header is included. If a public header such as `ssl.h` (which includes it at line 13) gets pulled in before `common.h` defines the opt-out, the macro is already fixed to the `private_` form for that unit. I checked that `rsa.c` includes `common.h` first. I did not verify the include order of every library file.

**The counter-case.** Several files use `MBEDTLS_PRIVATE(...)` and do not define the opt-out. These are treated as external users and go through the escape hatch:
- `programs/ssl/ssl_context_info.c:553-568` (built per `programs/Makefile:325` and `programs/ssl/CMakeLists.txt`)
- `tests/suites/test_suite_psa_crypto.function` and `test_suite_x509write.function`

These compile because the struct and the access expand to the same `private_` name. They are exactly the code that would break if a minor release renamed or reordered a field. `ssl.h:5159-5169` also marks direct access, even via the opt-out, as deprecated and unsupported for user code.