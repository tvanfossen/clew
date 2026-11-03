**What it accomplishes.** `MBEDTLS_PRIVATE(m)` is defined in `include/mbedtls/private_access.h:14-17`. By default it expands to `private_##m`, so the member is declared as `private_m` in the public header. The effect is that plain `ctx->m` fails to compile for anyone outside the library. The name is the only thing that changes. The layout does not, so the mangling is not an ABI change. What it does is make the member name a visible, greppable signal that the member has no stability promise. The 3.0 migration guide says so directly: accessing `bar.MBEDTLS_PRIVATE(foo)` is "a last resort… at your own risk" and "likely to break in a future minor version" (`docs/3.0-migration-guide.md:74`).

**It is a naming barrier, not an access control.** Both the declaration and the use go through the same macro, so `ctx->MBEDTLS_PRIVATE(foo)` resolves to `ctx->private_foo` and compiles. The header's own warning on `mbedtls_ssl_handshake_step`-style APIs says this explicitly: `ssl->MBEDTLS_PRIVATE(state)` still works (`include/mbedtls/ssl.h:5163`). Downstream code can reach any member; it just has to spell the access out.

**Where the opt-out is turned on.** `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined in exactly three kinds of place (verified by grep over the whole tree):

| Where | What it does |
|---|---|
| `library/common.h:132` | Defined for every library translation unit that includes it. 129 of the library's files include it. |
| `programs/ssl/ssl_server2.c:8`, `programs/ssl/ssl_client2.c:8` | Defined at the top, before `ssl_test_lib.h`. |
| Nothing else | No CMake, Makefile, or `-D` flag sets it. |

**What that means for the code in those places.** Inside those translation units `MBEDTLS_PRIVATE(m)` becomes plain `m`, so the code can write `ctx->grp.id` directly (`library/ecdh.c:150`) or `crt->ca_istrue` (`library/x509_crt.c:3306`). Two things follow:

- **The define has an ordering requirement.** `private_access.h` is guarded, so the first inclusion decides the expansion. Struct members are expanded when the public header is parsed. `common.h` must therefore come before any public header that declares these structs. The library files I checked do this. `ecdh.c` includes `common.h` at line 15, its first `#include`, and `ssl_tls.c` includes it at line 12, before `mbedtls/ssl.h` at line 18. A `.c` file that included a public header first would silently get the mangled names, and then its plain accesses would fail to compile. Two library files do not include `common.h` at all (`ecp_curves_new.c`, `ssl_debug_helpers_generated.c`). I did not check whether they touch these members.
- **The example programs get full access.** `ssl_server2.c` and `ssl_client2.c` read internal state without the explicit spelling.

**The other in-tree users do not get the opt-out.** The rest of the tree uses the explicit spelling, which compiles under the default setting:

- `programs/ssl/ssl_context_info.c:553-568` uses `ciphersuite_info->MBEDTLS_PRIVATE(flags)` and does not define the opt-out. I confirmed by preprocessing that the `#else` branch is active, and that the access becomes `private_flags`, which matches the struct's `private_flags`.
- `programs/fuzz/fuzz_dtlsserver.c:138` uses `ssl.MBEDTLS_PRIVATE(next_record_offset)`.
- `tests/suites/test_suite_x509write.function:763` uses `ctx.MBEDTLS_PRIVATE(extensions)`.

So the convention is that library internals and two example programs use the plain names, and everything else must use the explicit spelling, which the project treats as the deprecated route. The `ssl.h` warning and the migration guide both say the same thing.

**Caveats.** I did not build the programs; the `gcc -E` check only confirmed the preprocessing of `ssl_context_info.c`. I also did not trace how the x509write test translation unit ends up with the names it uses, beyond the explicit spelling.