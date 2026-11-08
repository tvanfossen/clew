**What it does.** `MBEDTLS_PRIVATE(member)` is a macro in `include/mbedtls/private_access.h`. Its definition is gated on `MBEDTLS_ALLOW_PRIVATE_ACCESS` (line 14):

- **Default (macro not defined):** `MBEDTLS_PRIVATE(member)` expands to `private_##member` (line 15). The struct member is really named `private_member`, so `ctx->member` fails to compile in application code.
- **Opt-out defined:** it expands to `member` (line 17), so the name is public again.

Declarations and uses both go through the macro, so the library's own code stays consistent either way. For example, `mbedtls_cipher_get_iv_size` in `include/mbedtls/cipher.h:724` reads `ctx->MBEDTLS_PRIVATE(cipher_info)`.

The purpose is to stop applications from coupling to internals. A user who writes `ctx->iv_size` gets a compile error instead of silently depending on a field that can be renamed or rearranged in a later release. This is API hygiene, not a security boundary. The struct definitions remain in the public headers, so `sizeof`, stack allocation and layout are still visible. The migration guide describes it the same way: "as a last resort" you can write `bar.MBEDTLS_PRIVATE(foo)` (`docs/3.0-migration-guide.md`).

**Who the opt-out is for.** The define is turned on in three places in this tree:

| Location | Line | Who it covers |
|---|---|---|
| `library/common.h` | 132 | The library itself. This is the internal header it uses, so library code gets direct member access. |
| `programs/ssl/ssl_client2.c` | 8 | The SSL client test/example program. |
| `programs/ssl/ssl_server2.c` | 8 | The SSL server test/example program. |

Consequences:

- **Inside the library**, member access is unrestricted. Changing a member name is a refactor, and nothing outside the library is expected to depend on the member.
- **In the two `programs/ssl` tools**, which are outside the library, the rule is off. They can read and write internals directly, which is what a test harness usually needs. Those two files are therefore coupled to the struct layout, so changes to those members will break them.
- **Everywhere else** (applications and integrators), the default applies and direct member access is a compile error unless they define the macro themselves before including the headers.

**Limits of what I could confirm.** The index shows `library/common.h:132` as a plain `#define` with an empty expansion, but not the surrounding condition. I also could not confirm that every library source includes `common.h` before the public headers, so I can't say whether every library translation unit gets the opt-out. The `ssl_client2.c`/`ssl_server2.c` lines are present, but I could not read the bodies to see which members they actually touch.