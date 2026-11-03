**What it does.** `MBEDTLS_PRIVATE(x)` is a rename, not an access check. `include/mbedtls/private_access.h:14-18` defines:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Every struct member is declared as `MBEDTLS_PRIVATE(foo)`, so by default the field is really named `private_foo`. Code that writes `ctx.foo` fails to compile because no such field exists. The layout is unchanged. What changes is the name, so the library can reorganise private fields without it looking like a public API change. It is a deterrent, not a security boundary: anyone can write `ctx.MBEDTLS_PRIVATE(foo)` and it compiles. `docs/3.0-migration-guide.md:74` documents that spelling as a "last resort … at your own risk".

**Who it is for.** The macro's audience is application developers. They get a compile error if they reach into a struct, and the spelled-out escape hatch is a visible, greppable admission that they are relying on internals. Library code is not the audience. It opts out.

**Where the opt-out is turned on in this tree:**

| Where | How | Effect |
|---|---|---|
| `library/common.h:132` | Unconditional `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Every library translation unit gets plain field names. |
| `programs/ssl/ssl_client2.c:8` | Defined before the first include | That program gets plain names. |
| `programs/ssl/ssl_server2.c:8` | Defined before the first include | That program gets plain names. |

I checked the library side. Every `library/*.c` file includes `common.h` before any public header, either directly or through `ssl_misc.h` (`ssl_debug_helpers_generated.c`). The exception is `ecp_curves_new.c`, which has no includes and no field access. So library code is consistent.

The opt-out must come before the first `mbedtls/` include in a translation unit, because the struct declarations are mangled as soon as a public header is read. `ssl_server2.c` and `ssl_client2.c` put it on line 8, ahead of `ssl_test_lib.h`, which is why it works there.

**What the non-opted-out code does.** Two places reach into private fields without the opt-out, using the escape-hatch spelling:

- `programs/ssl/ssl_context_info.c:553-568` uses `ciphersuite_info->MBEDTLS_PRIVATE(flags|cipher|mac)`.
- `programs/fuzz/fuzz_dtlsserver.c:138` uses `ssl.MBEDTLS_PRIVATE(next_record_offset)`.

These compile because both the struct and the access are mangled the same way. They are coupled to the internal field names, so they break if a field is renamed or moved. That is the risk the migration guide describes, and it is the cost of the escape hatch, not a bug in the macro.

**Caveat on the header itself.** `include/mbedtls/ssl.h:5159-5169` says direct access is deprecated even with `MBEDTLS_ALLOW_PRIVATE_ACCESS` defined, and could break in any future release. The opt-out is for the library and its own tools, not for supported external use.