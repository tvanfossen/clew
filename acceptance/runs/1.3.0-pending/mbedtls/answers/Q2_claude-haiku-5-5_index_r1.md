**What it does.** `MBEDTLS_PRIVATE(member)` is defined in `include/mbedtls/private_access.h:14-18`. Without the opt-out it expands to `private_##member`, so a field written as `MBEDTLS_PRIVATE(flags)` in a public header is actually named `private_flags` to any translation unit that includes it. Code that writes `ctx->flags` then fails to compile, while `ctx->MBEDTLS_PRIVATE(flags)` compiles everywhere. It is a source-level rename only: the struct layout and ABI do not change, so the define cannot alter binary compatibility.

**Who it is for.** Mostly the library's maintainers. Renaming the field gives them room to change internals without breaking callers who never meant to touch them, and it turns accidental access into a compile error. The migration guide (`docs/3.0-migration-guide.md:74`) describes the escape hatch as "at your own risk" and says such code is likely to break in a future minor version. The comment in `include/mbedtls/ssl.h:5159-5169` calls direct access deprecated.

**Where the opt-out is turned on in this tree.**

| Location | Effect |
|---|---|
| `library/common.h:132`, `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Unconditional for every library `.c` that includes `common.h` (about 129 files). Inside the library, `MBEDTLS_PRIVATE(x)` expands to the real `x`. |
| `programs/ssl/ssl_server2.c:8` | Defined before `ssl_test_lib.h`, so this program reads real SSL fields. |
| `programs/ssl/ssl_client2.c:8` | Same as above. |

Nothing else in the tree defines it. The test suites (`tests/suites/test_suite_x509write.function`, `test_suite_psa_crypto.function`) and `programs/ssl/ssl_context_info.c` use the `MBEDTLS_PRIVATE(...)` spelling without the opt-out, so they reach fields through the mangled `private_*` names. That works because the header and the use site expand the same way.

**What this means for the opted-in code.**

- **Library sources** depend on include order. `common.h` must come before any public header in each library `.c`. If a public header came first, its struct would get `private_*` names while the `.c` body expanded to the real names, and the build would fail. Spot checks show `common.h` is the first include in `ecp.c:32`, `ssl_tls.c:12`, `x509_crt.c:20`, `md.c:12` and `ssl_msg.c:13`. A new library file has to keep that ordering.
- **`ssl_server2.c` and `ssl_client2.c`** are coupled to internal SSL layout. They are in-tree, so a rename breaks their build rather than failing silently. That protects the tree, but it also means these two programs are the places to update when internal fields change.
- **The library itself** cannot be affected by the public mangling, because `common.h` opts it in unconditionally. A user cannot opt out of the library's own access, only out of the rename for their own code.

I used grep for the macro rather than `dossier`, since this is a macro and not a named symbol. I did not build the tree or confirm the compile-error behaviour by running it; that part is from reading the expansion rules.