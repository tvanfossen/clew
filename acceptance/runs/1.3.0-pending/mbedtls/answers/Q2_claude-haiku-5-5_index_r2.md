**What it does.** `include/mbedtls/private_access.h` defines the wrapper:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

By default, a struct member written as `MBEDTLS_PRIVATE(state)` is declared and named `private_state`. Code that reaches into `ssl->state` directly stops compiling, so the field is effectively private. The library can rearrange or rename internals without it counting as an API break. The wrapper is an API-hygiene device, not a security boundary: anyone can define the opt-out.

**Who it's for.**

- **Application authors (default).** They get the renamed `private_*` fields and cannot reach internals by accident. The one documented way to get direct access is to define `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including mbedtls headers. `include/mbedtls/ssl.h:5159-5169` says even that is deprecated and may break in any release, and asks people who need it to raise an issue instead.
- **The library itself.** `library/common.h:132` defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` unconditionally. `common.h` is included by most `library/*.c` files, so the library's translation units see the real member names. That opt-out is internal to the build and never reaches users, because `common.h` is a library-private header.

**Where the opt-out is turned on in this tree.**

| Location | Effect |
|---|---|
| `library/common.h:132` | All library TUs that include it get real member names. |
| `programs/ssl/ssl_client2.c:8` | Defined before any include. Direct field access is allowed. |
| `programs/ssl/ssl_server2.c:8` | Same. |

Everything else gets the private names. Examples:

- `programs/ssl/ssl_context_info.c:553-568` uses `MBEDTLS_PRIVATE(flags|cipher|mac)` with no opt-out, so it compiles against `private_*` names.
- `programs/fuzz/fuzz_dtlsserver.c:138` uses `ssl.MBEDTLS_PRIVATE(next_record_offset)` with no opt-out in its TU.
- `tests/suites/test_suite_x509write.function:763` uses `ctx.MBEDTLS_PRIVATE(extensions)`. It does not include `common.h` (its `x509_internal.h` include does not pull it in), so it also resolves to `private_extensions`.

**What that means for the code in those places.**

- The two `ssl_*2.c` programs are the only non-library code that is allowed to depend on the real layout. If an `ssl` struct member is renamed or moved, those programs break at compile time, and the library's own code breaks with them.
- Everything else uses the wrapper, which expands to the private name. Because the expansion is the same wrapper in both modes, a test or tool written with `MBEDTLS_PRIVATE(x)` compiles either way. A test written with a bare `x` would break outside library builds.

**Caveat.** The macro is expanded when the struct header is first parsed, so the opt-out must be defined before the first mbedtls header in a translation unit. The library depends on `common.h` coming first. I checked that for `common.h` itself but did not audit every library `.c` file.