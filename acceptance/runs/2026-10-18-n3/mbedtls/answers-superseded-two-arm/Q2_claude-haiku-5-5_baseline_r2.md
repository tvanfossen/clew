**What it does.** `include/mbedtls/private_access.h` defines the macro two ways:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member   /* default */
#else
#define MBEDTLS_PRIVATE(member) member             /* opt-out */
#endif
```

Every struct member in the public headers is spelled `MBEDTLS_PRIVATE(name)` in its declaration. By default the member is actually named `private_name`. Application code that writes `ctx->name` gets a compile error, so the field is not part of the API. It is a compile-time speed bump, not a security boundary: anyone can define the opt-out or write `ctx->MBEDTLS_PRIVATE(name)` explicitly. Its purpose is to let Mbed TLS rearrange internals across minor releases without breaking callers who depended on field names. `docs/3.0-migration-guide.md:74` describes direct access as a last resort done "at your own risk", and `ssl.h:5159-5170` calls direct state access deprecated.

**Who the opt-out is for.** The opt-out is turned on in three places:

| Location | How | Who it covers |
|---|---|---|
| `library/common.h:132` | Unconditional `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | All library `.c` and internal `.h` files that include `common.h` |
| `programs/ssl/ssl_server2.c:8` | Defined before any include | The server test program |
| `programs/ssl/ssl_client2.c:8` | Defined before any include | The client test program |

The library's own sources are the main beneficiaries. For example, `library/ssl_tls.c` includes `common.h` at line 12, before `mbedtls/ssl.h` at line 18. Because the macro is evaluated when a header is parsed, the struct's members are declared as real names in that translation unit. Code in the same translation unit can then use `ssl->state` or `info->MBEDTLS_PRIVATE(key_exchange)` directly. The order matters: if a public header were parsed before the define, the struct would have `private_x` members while the library code expected `x`, and the build would fail. The two test programs define the macro before `ssl_test_lib.h` pulls in the headers, for the same reason.

The opt-out is per translation unit, not a build option. Nothing in the CMake or Makefile files sets it. An out-of-tree consumer gets the private names unless it defines the macro itself before including any Mbed TLS header.

**One nuance.** `programs/ssl/ssl_context_info.c` uses `ciphersuite_info->MBEDTLS_PRIVATE(flags)` at line 553 and related lines, but never defines the opt-out. That compiles, because the struct declaration in `ssl_ciphersuites.h` expands the same way, so both sides refer to `private_flags`. The program is therefore reaching into internals by spelling the private name explicitly, without the opt-out. That works but is fragile, and it is the one spot where the macro is used as a deliberate escape hatch rather than a library-internal convenience.