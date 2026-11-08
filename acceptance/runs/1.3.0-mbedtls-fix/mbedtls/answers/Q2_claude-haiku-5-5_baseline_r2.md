**What the macro does.** `MBEDTLS_PRIVATE(member)` is defined in `include/mbedtls/private_access.h:14-18`:

- Without `MBEDTLS_ALLOW_PRIVATE_ACCESS`, it expands to `private_##member`.
- With the define, it expands to plain `member`.

Because the same macro is applied where the struct is declared and where it is used, the mangling is consistent. Code that writes `ctx->MBEDTLS_PRIVATE(foo)` compiles either way. Code that writes `ctx->foo` compiles only when the define is set. The result is a compile-time barrier: an application that reads `ctx->foo` gets "no member named foo" and has to pick a supported API instead.

It is a naming barrier, not access control. Anyone can write `ctx->private_foo` or define the macro themselves. `docs/3.0-migration-guide.md:74` says so: direct access is "at your own risk" and may break in a minor release. The point is to keep internal layout free to change and to make accidental coupling fail at build time.

**Who the opt-out is for.** The define is turned on in three places in this tree:

| Where | What it means |
|---|---|
| `library/common.h:132` | Every library `.c` file. 107 of the 109 `library/*.c` files include `common.h`, and it is the first Mbed TLS header they pull in, so the internal code sees real member names. I did not check the two that don't (`ecp_curves_new.c`, `ssl_debug_helpers_generated.c`). |
| `programs/ssl/ssl_client2.c:8` and `ssl_server2.c:8` | The test client and server define it before `ssl_test_lib.h`, so they can read and write plain fields. |

Other in-tree users take a different route. `programs/ssl/ssl_context_info.c` does not define the opt-out. It spells out `ciphersuite_info->MBEDTLS_PRIVATE(flags)` and similar. I ran `gcc -fsyntax-only` on it without the define and it compiled with rc=0. The preprocessed output shows `private_flags`, which is the mangled name that the struct declaration also produced. `programs/fuzz/fuzz_dtlsserver.c:138` does the same with `ssl.MBEDTLS_PRIVATE(next_record_offset)`.

**Consequences for those places.**
- In the library and the two test programs, field names are the real names. Renaming a field only requires updating the code in the tree.
- Explicit `MBEDTLS_PRIVATE(...)` in `ssl_context_info.c` and the fuzzer is a deliberate reach into private state that keeps working without the opt-out. It is still fragile for the same reason the migration guide gives.
- The guard is an include-guarded header. Whichever file first includes `private_access.h` fixes the mode for that translation unit. That is why `common.h` must be included before any public header. This follows from reading the guard, and I did not test a file that breaks the ordering.
- `include/mbedtls/ssl.h:5160-5166` calls direct access to `ssl->state` deprecated and says the opt-out is no longer the recommended route. The public header and the migration guide both treat it as an internal mechanism for the library and the tests, not a supported API for applications.