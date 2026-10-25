**Short answer:** `MBEDTLS_PRIVATE(x)` is a rename guard, not access control. It exists so that application code can't reach into struct internals by accident, which leaves the library free to change those layouts. The library itself and a few programs are the ones that opt out.

**Mechanism** (`include/mbedtls/private_access.h`):

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Every public struct declares its members as `MBEDTLS_PRIVATE(name)`. By default those members are named `private_name`, so `ctx->state` fails to compile and `ctx->MBEDTLS_PRIVATE(state)` is the only spelling that works. Defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before the headers are included restores the plain names.

**Who it is for:**

| Audience | Opt-out? | Where |
|---|---|---|
| External applications | No (default) | Plain member access breaks at compile time. `ssl.h:5163` documents direct access as deprecated and not guaranteed to survive future releases. |
| Library sources | Yes, globally | `library/common.h:132` defines the macro. Every `library/*.c` includes `common.h` except `ecp_curves_new.c` and `ssl_debug_helpers_generated.c`, and neither uses the macro. Internal headers such as `library/ssl_ciphersuites_internal.h` use `MBEDTLS_PRIVATE(...)` and inherit the opt-out. |
| `programs/ssl/ssl_server2.c`, `ssl_client2.c` | Yes, per file | Each defines the macro on its first line, before any include. |
| `programs/fuzz/fuzz_dtlsserver.c` | Yes, indirectly | Includes `common.h`, so it gets the opt-out. It uses `ssl.MBEDTLS_PRIVATE(next_record_offset)` directly. |
| `programs/ssl/ssl_context_info.c` | No, and does not need it | It has no opt-out and does not include `common.h`. It writes `ciphersuite_info->MBEDTLS_PRIVATE(flags)`, which expands to `private_flags` in both the header and the program, so it compiles. |

**What this means in practice:**

- **Library code** is unaffected. Inside the library, `MBEDTLS_PRIVATE(x)` is just `x`, so the opt-out costs nothing.
- **The two SSL test clients** are unaffected because they define the macro themselves before including anything. Their access is the same as library access.
- **`ssl_context_info.c`** is the instructive case. It shows the portable pattern for external code that needs a field: write `MBEDTLS_PRIVATE(field)` yourself. That works whether or not the opt-out is on.
- **The build sets no global flag.** A grep of the tree found no `-D` or CMake definition, so the opt-out is only per-translation-unit. Each file that needs raw names has to declare it.

**Caveat on "guard":** the macro is trivially bypassed by defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before the includes, and the fields are still in the struct. It is a deliberate friction point that makes any reliance on internals visible in the source. Anyone who opts out has taken on the risk that the field moves or disappears in a later release.

I did not check whether `tests/suites/*.function` (which matched my search) opt out or use the macro, so I have not included them in the table.

A hook output during this session asked me to call a `dossier` tool. No such tool is available here, so I ignored it and worked from the files.