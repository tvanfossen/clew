**What it does.** `include/mbedtls/private_access.h` is a two-line macro. Without `MBEDTLS_ALLOW_PRIVATE_ACCESS`, `MBEDTLS_PRIVATE(member)` expands to `private_##member`. With it defined, the macro expands to `member`. Struct declarations use the macro for each private field, so a field `flags` is declared as `private_flags` in a default build. A consumer who writes `cfg->flags` gets "no member named flags". The field is still there under the mangled name, and `cfg->MBEDTLS_PRIVATE(flags)` works.

So this is a naming guard, not an access control. C has no member visibility, and the spelling is the only thing standing between a user and the field. The migration guide (`docs/3.0-migration-guide.md:74`) calls direct access a last resort "at your own risk". The guard keeps the internal layout free to change in minor releases and makes accidental use fail to compile. It does not change the struct layout, so the ABI is the same either way.

**Who it is for.**

- **Users of the library.** They should use accessors. The define is available to them but is documented as deprecated (`include/mbedtls/ssl.h:5163`).
- **The library itself.** `library/common.h:132` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` globally. Every `library/*.c` file includes `common.h` as its first include, so the library sees the real field names. The two exceptions, `ecp_curves_new.c` and `ssl_debug_helpers_generated.c`, do not use the macro.
- **In-tree programs and tests.** `programs/ssl/ssl_server2.c` and `ssl_client2.c` define it on line 8, before `ssl_test_lib.h`. `tests/suites/*.function` and `tests/src/certs.c` pick it up through `common.h`. `programs/fuzz/fuzz_dtlsserver.c` also gets it through `common.h`.

**What that means for the code in those places.**

- The define is read when the struct header is parsed, not at the use site. A translation unit that defines it after an mbedtls header has already declared the struct gets mismatched names and fails to compile. That is why `common.h` must come first, and why the programs define the macro before anything else.
- `programs/ssl/ssl_context_info.c` writes `ciphersuite_info->MBEDTLS_PRIVATE(flags)` without defining the opt-out. That works because its `ssl_ciphersuites.h` declaration was also parsed without the define, so both sides expand to `private_flags`. The spelling is only the escape hatch; it is not a grant of access.
- `programs/ssl/ssl_context_info.c` is built (`programs/ssl/CMakeLists.txt:13`), so it compiles against the mangled names as a consumer would.

In short, the macro is a compile-time naming convention. The library and its own tools opt out with `common.h`, and a consumer who uses the spelling anyway takes on the risk the migration guide describes.