**What it does.** `MBEDTLS_PRIVATE(member)` is a macro in `include/mbedtls/private_access.h:15`. In the default configuration it expands to `private_##member`, so a public struct field is renamed. Writing `ctx->MBEDTLS_PRIVATE(cipher_info)` compiles to `ctx->private_cipher_info`. The field is still in the header, but its name is changed, so code that reaches into it by the plain name fails to compile. C has no access control, so this rename is the only barrier. The header's file doc calls it a "Macro wrapper for struct's members," and `library/common.h:132` says the members "are private and should not be accessed by the user."

**The gate.** `private_access.h:14-18` selects the expansion on `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

```
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS   -> MBEDTLS_PRIVATE(m) = private_##m   (renamed)
#ifdef  MBEDTLS_ALLOW_PRIVATE_ACCESS   -> MBEDTLS_PRIVATE(m) = m             (plain name)
```

**For whom.**

- **Default (no define):** external applications that include mbedtls headers. They cannot use the field names. They must go through the accessor functions, such as `mbedtls_ssl_get_hostname`, `mbedtls_ssl_conf_get_endpoint` and `mbedtls_ssl_is_handshake_over`. Those accessors are in the index, and their bodies use `MBEDTLS_PRIVATE` internally.
- **Opt-out:** the library itself and its own sample programs. Inside that code the field is accessed by its real name.

**Where the opt-out is turned on in this tree.** It is a hard-coded `#define`, not a build option. It has no Kconfig or config-header entry, and the index reports its origin as undeclared.

| Location | Scope |
|---|---|
| `library/common.h:132` | Library-internal header. Any library `.c` that includes it gets direct member access. |
| `programs/ssl/ssl_client2.c:8` | Sample client, defined at the top of the file. |
| `programs/ssl/ssl_server2.c:8` | Sample server, defined at the top of the file. |

For those files, `conf->max_tls_version`-style accesses are plain field accesses. The sample programs can reach the internals of the SSL structs, which is the point of the opt-out.

**What this means for the code in those places.**

1. The library's own `.c` files see the real field names. They can change internal layout without breaking an accessor layer, and they are not held to the public surface.
2. Opting out is a per-translation-unit decision, so it is only as broad as the `.c` file that defines it. Public headers are still expanded under whatever definition was in effect when they were first included. If a library `.c` includes an mbedtls header before `common.h`, the header's inline accessors expand with the renaming. I did not verify the include order in each file, so treat that as a check to run.
3. The sample programs are not an example for applications. They reach into `ssl` and `conf` internals, so they break if the layout changes and are not a supported API.

**Limits of what I could confirm.** The index has no record of the default configuration header, so I could not check whether anything else enables the opt-out. The `ssl.h:5163` comment that mentions defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` was cut off in the search snippet, so I have not read its full text.