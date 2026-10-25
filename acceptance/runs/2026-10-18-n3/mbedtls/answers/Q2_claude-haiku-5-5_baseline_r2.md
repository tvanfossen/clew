**What it accomplishes.** `MBEDTLS_PRIVATE(member)` is a preprocessor rename. `include/mbedtls/private_access.h:14-18` expands it to `private_##member` unless `MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined, in which case it expands to `member`. So a struct field declared as `MBEDTLS_PRIVATE(state)` is really named `private_state` for ordinary builds. Code that writes `ssl->state` then fails to compile, and the field's name is no longer part of the public contract, so the library can rearrange or rename internals without breaking callers. It is a source-level barrier, not access control in C: anyone can write `ssl->private_state` or define the macro themselves.

**Who it's for.** The default is "outside users get the renamed fields." The opt-out is for the library itself and a few in-tree programs:

| Where | What it does |
|---|---|
| `library/common.h:132` | Defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` for the whole library. Library `.c` files include it first (e.g. `library/ssl_tls.c:12`, before any `mbedtls/*.h`), so they see the real member names. |
| `programs/ssl/ssl_server2.c:8` | Defines it directly before `ssl_test_lib.h`. |
| `programs/ssl/ssl_client2.c:8` | Same. |

What this means for those places:
- Library code uses the plain field names and compiles as it did before the wrapper existed. Its internals are free to change together, since it's built from the same tree.
- `ssl_server2.c` and `ssl_client2.c` also get direct field access, so they break if internal layout changes. They're in-tree, so they're kept in sync with the library, but they are not protected by the stability promise.
- Test suites (`tests/suites/*.function`) do not use the global define. They write `MBEDTLS_PRIVATE(x)` at each access, which works in either mode. That's why a grep for the opt-in finds nothing under `tests/`.

**Ordering caveat (from reading the code, not compiled).** The choice is fixed when `private_access.h` is first included, and the struct declarations are expanded at that point. A translation unit that includes any public header before `common.h` would keep the `private_` names and fail on direct access. The library's include order avoids this.

**Guidance for users.** `include/mbedtls/ssl.h:5163` marks direct access, including defining the macro, as deprecated and unsupported. `docs/3.0-migration-guide.md:74` calls `bar.MBEDTLS_PRIVATE(foo)` the last resort, at your own risk, and notes that the 3.6 LTS tries to keep it stable.