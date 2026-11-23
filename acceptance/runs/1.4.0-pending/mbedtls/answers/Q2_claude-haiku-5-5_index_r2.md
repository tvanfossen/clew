**What it does.** `MBEDTLS_PRIVATE(member)` is a macro defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Struct fields are declared as `MBEDTLS_PRIVATE(foo)`, so by default a field `foo` is actually named `private_foo`. Code outside the library that writes `ctx->foo` fails to compile, and code that writes `ctx->MBEDTLS_PRIVATE(foo)` compiles only because the same macro produced the mangled name. It is a compile-time guard, not an access-control mechanism. The header comment in `library/common.h:127-131` gives the intent: the members are private and should not be accessed by users.

**For whom.** The guard is for application developers and their code. The 3.0 migration guide (`docs/3.0-migration-guide.md:70-74`) tells them to use accessor functions, and to reach a field only as a last resort via `bar.MBEDTLS_PRIVATE(foo)`, "at your own risk" and with no stability promise. The `ssl.h:5159-5169` warning says the same about `ssl->state`: direct access is deprecated and could break in any release.

**Where the opt-out is turned on.** I found it in three places (a repo-wide grep for `MBEDTLS_ALLOW_PRIVATE_ACCESS`, including build files, returned only these):

| Location | Effect |
|---|---|
| `library/common.h:132` | Defines it for the whole library. Library `.c` files that include `common.h` before any mbedtls header get direct field access. I checked `ecdh.c`, `md.c` and the rest of the library files that use `MBEDTLS_PRIVATE`; each includes `common.h` first. `common.h` does not itself pull in `private_access.h`, so the define lands before the guard is evaluated. |
| `programs/ssl/ssl_server2.c:8` | Defined before any mbedtls include, so the sample server gets direct access. |
| `programs/ssl/ssl_client2.c:8` | Same, for the sample client. |

**What this means for the code in those places.** The library and the two sample programs are the only code that gets to write `ctx->foo` directly. Everything else is still forced through the `MBEDTLS_PRIVATE` spelling or through accessors.

Two points to watch:

- The opt-out is decided once per translation unit, at the first inclusion of `private_access.h`. A file that includes any mbedtls header before defining the macro gets the mangled names, and that is a silent include-order trap.
- `programs/ssl/ssl_context_info.c` (lines 553-568) and `programs/fuzz/fuzz_dtlsserver.c:138` write `MBEDTLS_PRIVATE(...)` explicitly but do not define the opt-out. They compile in the default mode because the headers declare those fields with the same macro, so the names match. These two files are therefore not using the opt-out. They are written to the "last resort" spelling, which is the spelling that keeps working across builds.

I did not build the tree, so the compile behaviour above comes from reading the macro and the include order, not from a build run.