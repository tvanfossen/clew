**What it does.** `MBEDTLS_PRIVATE(member)` is a name-mangling macro, defined in `include/mbedtls/private_access.h:14-18`:

- Without `MBEDTLS_ALLOW_PRIVATE_ACCESS`: `MBEDTLS_PRIVATE(foo)` becomes `private_foo`.
- With it defined: it becomes `foo`.

Headers apply it at the declaration (e.g. `struct mbedtls_ssl_ciphersuite_t` in `include/mbedtls/ssl_ciphersuites.h:448-459` declares `MBEDTLS_PRIVATE(flags)`), and code applies it at each access. So in a default build a user writing `ctx->flags` gets a compile error, since the member is named `private_flags`. The migration guide says this directly: "Attempting to access a private field directly will result in a compilation error" (`docs/3.0-migration-guide.md:74`).

It is a source-level speed bump, not access control. Struct layout is identical either way; only the identifier changes. Anyone can define the macro, so it doesn't stop a determined caller. Its purpose is to make the access loud and greppable, and to mark the layout as unstable. The migration guide says fields are not part of the stable API and may change in minor releases, and the `ssl.h:5159-5169` warning calls direct access to `ssl->MBEDTLS_PRIVATE(state)` deprecated.

**For whom.** Mainly application authors. They get the mangled names, and the only sanctioned way in is to spell `MBEDTLS_PRIVATE(...)` explicitly as a last resort. The opt-out exists for the library and for in-tree programs that are built together with the headers.

**Where the opt-out is turned on in this tree:**

| Location | Effect |
|---|---|
| `library/common.h:132` `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Every library `.c` that includes `common.h` gets real member names. The checked files (`ssl_msg.c`, `ecdh.c`, `md.c`, `x509_crt.c`) include it first. |
| `programs/ssl/ssl_server2.c:8` | Defined before `ssl_test_lib.h`, so the server can touch internal fields directly. |
| `programs/ssl/ssl_client2.c:8` | Same, for the client. |

Two details matter here:

- **Ordering is load-bearing.** `private_access.h` is guarded, so the macro is fixed the first time that header is included. A library `.c` that included a public header before `common.h` would silently get mangled names. The checked files avoid that. `ecp_curves_new.c` and `ssl_debug_helpers_generated.c` don't include `common.h`, but they don't touch struct members either.
- **`common.h` is internal.** It lives under `library/`, so the opt-out never reaches users who only include `include/mbedtls/`.

**What it means for the code in those places:**

- **Library sources** read and write real fields such as `ctx->MBEDTLS_PRIVATE(grp)` → `ctx->grp`. They are compiled against the same headers they ship with, so a layout change is caught at build time.
- **`ssl_server2.c` and `ssl_client2.c`** are demo and test drivers that reach into the SSL state. They are built from the same tree, so they break at compile time on a layout change rather than at runtime. They are also the code the `ssl.h` warning is aimed at, so they are the places to fix first if the internals move.

**Places that do not opt out.** `programs/ssl/ssl_context_info.c` (lines 553-568), `programs/fuzz/fuzz_dtlsserver.c:138`, and the `tests/suites/*.function` files use `MBEDTLS_PRIVATE(x)` explicitly, without the define. They still compile because the header and the access site are mangled the same way within each translation unit. They are therefore written against `private_*` names, and they reach internals only through the documented last-resort spelling.