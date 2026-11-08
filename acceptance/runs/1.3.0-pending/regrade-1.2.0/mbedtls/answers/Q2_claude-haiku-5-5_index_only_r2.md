**Short answer:** `MBEDTLS_PRIVATE(member)` is a rename that makes struct fields inaccessible to ordinary C code. The opt-out is for the library and its own programs. Everyone else gets a deliberate, greppable escape hatch.

**Mechanism** (`include/mbedtls/private_access.h`, lines 14–18):

- **Default (`MBEDTLS_ALLOW_PRIVATE_ACCESS` not defined):** `MBEDTLS_PRIVATE(x)` expands to `private_x`. A field declared as `MBEDTLS_PRIVATE(nr)` is really named `private_nr`, so `ctx.nr` fails to compile.
- **Opt-out (`MBEDTLS_ALLOW_PRIVATE_ACCESS` defined):** `MBEDTLS_PRIVATE(x)` expands to `x`, and the field has its real name.

Example: `mbedtls_aes_context` declares its round count as `MBEDTLS_PRIVATE(nr)` (`include/mbedtls/aes.h`). The docs for the macro say the same thing in prose: structs in headers are public, but their members are private and should not be touched by users.

**What it accomplishes:** it turns "don't touch this" into a compile error. The library can change field names, layout or meaning without breaking callers who obeyed the rule, and any caller who did reach in breaks at build time instead of silently at runtime. The 3.0 migration guide documents the escape hatch: as a last resort, write `bar.MBEDTLS_PRIVATE(foo)`. That expands to `bar.private_foo` in user code, so it compiles, and it is searchable in the user's own codebase.

**Who turns the opt-out on in this tree** (every `#define` site of `MBEDTLS_ALLOW_PRIVATE_ACCESS`):

| Location | Who it covers |
|---|---|
| `library/common.h:132` | The library's own translation units, which pull in `common.h`. |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` test/sample program. |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` test/sample program. |

**What that means for those files:** in these translation units `MBEDTLS_PRIVATE(x)` is just `x`, so `ctx.x` compiles and reads or writes internal state directly. Those files are coupled to the real layout. A field rename breaks them at compile time, which is visible, but nothing shields them from internal changes. The library itself has no such shield.

**Caveats:**

- The index records the `#define` sites but not the guard around `library/common.h:132`. I could not confirm whether it is unconditional.
- The index does not show include order. The opt-out only works if the define comes before `private_access.h` is first included in a given translation unit. `ssl_client2.c` and `ssl_server2.c` define it at line 8, near the top, which fits that. I could not verify the includes that follow it.
- I did not check which internal fields the two `programs/ssl` files actually touch.