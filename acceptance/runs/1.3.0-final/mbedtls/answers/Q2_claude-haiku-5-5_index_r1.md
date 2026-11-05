**What it accomplishes:** `MBEDTLS_PRIVATE(member)` is a naming guard, not access control. `include/mbedtls/private_access.h` defines it two ways:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

By default, `ssl->MBEDTLS_PRIVATE(state)` becomes `ssl->private_state`, so code that touches a field directly fails to compile. The struct layout and the ABI are identical either way. The guard only changes the spelling the compiler sees. The point is to stop users from depending on fields that Mbed TLS may rename, reorder or remove. The 3.0 migration guide says so directly: direct field access "is likely to break in a future minor version" (`docs/3.0-migration-guide.md:74`), and the public header comments say the same (`include/mbedtls/ssl.h:5159-5169`).

**For whom:** the default protects external consumers. The opt-out is for the library itself and for in-tree programs that need field access.

**Where the opt-out is turned on in this tree:**

| Location | Effect |
|---|---|
| `library/common.h:132` | `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` is unconditional. Every library source includes `common.h` before the public headers. For example, `library/ssl_tls.c` includes `common.h` at line 12, before `mbedtls/ssl.h` at line 18. So library code reaches fields by their real names. |
| `programs/ssl/ssl_server2.c:8` | Defined before `ssl_test_lib.h`. The test server reads and writes fields directly. |
| `programs/ssl/ssl_client2.c:8` | Same, for the test client. |

What this means for the code in those places:

- **Library sources** can write `ssl->state` or `conf->min_tls_version` directly. This is an internal implementation detail, and it is the reason the struct members are declared in headers at all.
- **The two test programs** get the same privilege. Because the macro is per translation unit, a program has to define the symbol before its first Mbed TLS include. The define has to come before `ssl_test_lib.h`, and it does.
- **Everything else** (applications, other programs, downstream code) still gets `private_*` names. If they define the macro themselves, they opt out of the guard, and the header's deprecation note says that direct access is deprecated and may break in any release.

Two caveats. First, the opt-out is a C preprocessor switch, so it does not enforce anything. Any consumer can define it, and nothing stops it except the warning text and the 3.6 LTS ABI promise. Second, the macro appears in the public API as a convenience in the inline accessors. For example, `mbedtls_ssl_is_handshake_over()` at `include/mbedtls/ssl.h:5148` uses `ssl->MBEDTLS_PRIVATE(state)`. Those accessors compile for users, which is the reason the guarded spelling appears in public headers rather than being hidden inside the library.