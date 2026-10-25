**What it does.** `MBEDTLS_PRIVATE(m)` is a source-level guard on struct members. Its definition in `include/mbedtls/private_access.h:14-18` is:

- Default: `MBEDTLS_PRIVATE(member)` expands to `private_##member`. Public struct declarations use this macro, so a field `state` is actually named `private_state` in the header. Outside code writing `ssl->state` fails to compile.
- If `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined: it expands to the plain `member`.

It is a compile-time speed bump, not a security boundary. The layout is still in the header. It tells users that the layout is not a stable API. `docs/3.0-migration-guide.md:64-74` says minor releases may add, remove, reorder, or retype fields, and that `bar.MBEDTLS_PRIVATE(foo)` is a last resort "at your own risk." The `ssl.h:5159-5169` warning calls direct access deprecated.

**Who it's for.** Application code is the default audience. Library internals, the sample programs, and the tests are the exceptions that get the opt-out.

**Where the opt-out is turned on in this tree:**

| Location | What it means |
|---|---|
| `library/common.h:132` | Defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally, so every library `.c` that includes it sees real field names. This is the library's own view. |
| `programs/ssl/ssl_server2.c:8`, `programs/ssl/ssl_client2.c:8` | Defined before the first include. These sample programs read and write struct fields directly. |

Library use depends on include order. `library/ecdh.c` includes `common.h` at line 15, before the public `mbedtls/ecdh.h` at line 19, so the public struct is declared with real member names. Anything that includes a public header before `common.h` gets the `private_` names. I didn't check every library file for this. `library/pk_internal.h` doesn't include `common.h` itself, so it depends on its includer.

**Code that uses `MBEDTLS_PRIVATE(...)` explicitly without the opt-out.** These spellings compile in both modes because the declaration and the use expand the same way. Examples: `programs/ssl/ssl_context_info.c:553-568`, `programs/fuzz/fuzz_dtlsserver.c:138`, `library/x509_crt.c:3306`, `library/ecdh.c:150`, and the `tests/suites/*.function` files. The spelling is deliberate and greppable: it marks "this touches a private field on purpose."

**What this means for the opt-out sites.** In `ssl_server2.c`, `ssl_client2.c`, and all of `library/`, the code can touch any struct member directly. Changing a private field there breaks nothing at compile time. An outside user who defines the same macro gets the same access, with the same no-stability guarantee. Compatibility is only promised for the documented public fields. The samples and library rely on the same layout as the library version they are built with, which is why they build cleanly from the same tree.