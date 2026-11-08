**What it does.** `MBEDTLS_PRIVATE(m)` is a rename, not an access check. `include/mbedtls/private_access.h` defines it as:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Public structs in `include/` declare their fields through this macro, so by default `ctx->grp` does not exist and `ctx->private_grp` does. A consumer who writes `ctx->grp` gets a compile error, not a silent read of something that may change. This is API hygiene: it keeps the layout of public structs (for example `mbedtls_ssl_context`, `psa_hkdf_key_derivation_t`) free to change in a minor release without breaking callers who were reaching into fields. It is not a security boundary; the field is still there and can be read by its `private_` name. The migration guide (`docs/3.0-migration-guide.md:74`) says as much: it is "a last resort" done "at your own risk."

**For whom.** There are two audiences:

- **External consumers** get the renamed fields and are discouraged from touching them. `ssl.h:5159-5169` labels direct state access "deprecated" and asks users to file a request for an accessor instead.
- **The library itself** needs the real names. It opts out with `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`, which is set in `library/common.h:132`.

**Where the opt-out is turned on in this tree:**

| Location | How | Effect |
|---|---|---|
| `library/common.h:132` | Unconditional `#define` | Every `library/*.c` file that includes `common.h` sees real field names. `common.h` is the first include in essentially all of them. |
| `library/ssl_debug_helpers_generated.c` | Gets it indirectly: includes `ssl_misc.h`, which includes `common.h` | Same effect. |
| `programs/ssl/ssl_client2.c:8` | Defined before any include | Real names in this translation unit only. |
| `programs/ssl/ssl_server2.c:8` | Same | Same. |

`library/common.h` is not under `include/`, so the define does not reach consumers. The opt-out only applies in translation units that define it or include `common.h` before any public header.

**What it means for the code in those places:**

- The library's 129 `.c` files that include `common.h` compile against the real struct layout, so `ctx->MBEDTLS_PRIVATE(grp)` in `library/ecdh.c:150` becomes `ctx->grp`.
- `ssl_client2.c` and `ssl_server2.c` are test and sample binaries that read internals directly. They are not part of the public API contract.
- `programs/ssl/ssl_context_info.c` does not define the global opt-out. It writes `ciphersuite_info->MBEDTLS_PRIVATE(flags)` per access, which compiles against the `private_flags` name. This is the sanctioned per-access form: it reaches internals without a blanket opt-out and makes each access visible in the source.

**Caveat on the failure mode.** If a library file included a public header before `common.h`, the struct would be declared with `private_` names in that translation unit while the `MBEDTLS_PRIVATE(...)` uses expanded to real names. That should fail to compile, not change behavior silently. I did not find any such ordering in the tree; every library `.c` file I checked includes `common.h` first, or includes `ssl_misc.h`, which does.