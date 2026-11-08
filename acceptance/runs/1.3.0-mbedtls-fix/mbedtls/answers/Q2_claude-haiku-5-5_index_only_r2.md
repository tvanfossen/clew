**What it does.** `include/mbedtls/private_access.h` defines `MBEDTLS_PRIVATE(member)` and wraps struct members in it. Whether the wrapper changes the name depends on one macro, `MBEDTLS_ALLOW_PRIVATE_ACCESS`, which the header checks at lines 14–18:

- **Gate not defined (the default for outside code):** `MBEDTLS_PRIVATE(member)` expands to `private_##member`. The real member is renamed, so `ctx->MBEDTLS_PRIVATE(foo)` fails to compile for anyone who writes it. Outside code cannot reach the field by accident.
- **Gate defined:** `MBEDTLS_PRIVATE(member)` expands to `member`, and the field is reachable under its real name.

The member comments are also tagged this way. `ssl.h`, `bignum.h`, `ccm.h`, `gcm.h`, `rsa.h`, `ctr_drbg.h` and the PSA headers mark fields with `MBEDTLS_PRIVATE`, which tells a reader that the field is not part of the contract. The 3.0 migration guide says field access is a compile error and offers `bar.MBEDTLS_PRIVATE(foo)` only as a "last resort".

**Who it is for.** The header is for the library's own code. It protects the library's internal layout: the public structs stay usable and their fields can change without breaking applications that compile against them. The wrapper also makes the boundary visible to a reader.

**Where the opt-out is turned on.** The index finds three definitions of `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

| Site | What it means |
|---|---|
| `library/common.h:132` | The internal library header. Its doc says: "Allow library to access its structs' private members." Any library translation unit that includes it sees the real member names. |
| `programs/ssl/ssl_client2.c:8` | The client sample program defines the gate at the top of the file. |
| `programs/ssl/ssl_server2.c:8` | The server sample program does the same. |

For that code, `MBEDTLS_PRIVATE(x)` is just `x`, so it can read and write struct fields directly. Everywhere else the field name is mangled.

**What this means in practice:**
- Library sources get direct field access through `common.h`. That is the intended path.
- The two SSL programs also get it, so they can reach internals that outside applications cannot.
- The gate is a preprocessor guard, not an access-control boundary. The check is `#ifndef` / `#ifdef` with no config option behind it (the index marks it "undeclared"), so any translation unit can define it before including the headers. It works as a compile-time convention that keeps outside code honest, not as enforcement.

**Limits of this answer.**
- The index does not show include order. I could not confirm that `common.h` or the `#define` at `ssl_client2.c:8` / `ssl_server2.c:8` comes before the `private_access.h` include in each file.
- I did not confirm whether any test file defines the gate. The macro dossier lists only the three sites above.
- The migration guide's "last resort" text came from search snippets, not the full section.