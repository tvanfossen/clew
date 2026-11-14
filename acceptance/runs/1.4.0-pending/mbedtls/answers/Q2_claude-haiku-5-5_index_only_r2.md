**What it does.** `MBEDTLS_PRIVATE(member)` is a macro in `include/mbedtls/private_access.h:15`. Its default expansion is `private_##member`, so `ssl->MBEDTLS_PRIVATE(state)` becomes `ssl->private_state`. Public headers use it to rename struct members, so application code that writes `ctx->state` no longer compiles. The file's brief says it is a "Macro wrapper for struct's members," and the `library/common.h` documentation says the library may access its structs' private members, although they are publicly visible in headers, and that users should not access them.

The public headers also use it in the inline accessors. Examples are `mbedtls_ssl_is_handshake_over` (`ssl.h:5148`), `mbedtls_ssl_session_get_id_len` (`ssl.h:2812`), `mbedtls_ssl_get_hostname` (`ssl.h:4144`), `mbedtls_ssl_cache_get_timeout` (`ssl_cache.h:163`), and the `psa_get_key_*` / `psa_set_key_*` helpers in `psa/crypto_struct.h`. So the supported getters and setters are the public API, and the raw fields are not.

**The opt-out.** The macro has two definitions, selected by `#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS` (line 14 in `private_access.h`):

- Without the define: `MBEDTLS_PRIVATE(m)` → `private_m`. Members are renamed and hidden.
- With the define: `MBEDTLS_PRIVATE(m)` → `m`. Members keep their real names.

`MBEDTLS_ALLOW_PRIVATE_ACCESS` is defined in exactly three places in this tree:

| Where | Who it affects |
|---|---|
| `library/common.h:132` | The library's own sources. Any TU that includes `common.h` gets the real member names. |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` sample program. |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` sample program. |

**What this means for those places.** Inside the library and the two SSL sample programs, code can read and write struct fields directly, because the macro resolves to the real names. Everywhere else, which includes external applications and the test programs not listed, the fields are renamed and direct access fails to compile. The library's internal code is therefore not bound by the public accessor layer. Changes to those fields can break the library's own code, but not external code that only uses the public API.

**Caveats I could not settle from the index.**

- The `#ifndef` is evaluated when `private_access.h` is first included. If `common.h` is included after a public header has already pulled in `private_access.h`, the choice made there is fixed by include order. I did not check include order in each `.c` file.
- The index shows no enclosing condition around the `common.h` define, so it looks unconditional for any build that includes that header.
- The `ssl_client2.c` and `ssl_server2.c` definitions appear at the top of those files, before their includes, which suggests they are meant to take effect. I did not verify this against the include chain.