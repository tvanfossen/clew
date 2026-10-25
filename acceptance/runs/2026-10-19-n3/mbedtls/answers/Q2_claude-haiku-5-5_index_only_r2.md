**What it does.** `MBEDTLS_PRIVATE(member)` is a token-pasting wrapper defined in `include/mbedtls/private_access.h:14-18`. By default it renames the member: `MBEDTLS_PRIVATE(nr)` expands to `private_nr`. So `mbedtls_aes_context`'s round count (`aes.h:64-71`) is declared as `private_nr`, and code outside the library that writes `ctx.nr` fails to compile. The rename is the enforcement. Nothing changes in layout, so the ABI is unaffected. Only the spelling changes, which means the protection is against accidental access, not a security boundary. Anyone can still write `ctx.private_nr`.

**Who it's for.** The intended audience is application code built against the public headers. Those users get a compile error if they reach into a struct's internals, which keeps them from depending on fields that can change between releases.

**Where the opt-out is turned on.** `MBEDTLS_ALLOW_PRIVATE_ACCESS` is the switch. The index shows three places that define it:

| Location | Who gets direct member access |
|---|---|
| `library/common.h:132` | The library's own sources, to the extent they include this header before the public headers are parsed |
| `programs/ssl/ssl_client2.c:8` | The `ssl_client2` test/debug program |
| `programs/ssl/ssl_server2.c:8` | The `ssl_server2` test/debug program |

Two things this means for the code in those places:

- **The library and the two SSL test programs can read and write internals directly.** Their source uses names like `ctx.nr`, and those compile. Any change to the struct's field names will also break them silently only if the opt-out is removed; otherwise they just track the real names.
- **The opt-out is a plain `#define`, not a Kconfig symbol.** The index records it as "origin undeclared," so it isn't set through the configuration system. It's a source-level flag, so the three sites above are the only ones that make internals visible.

**Caveats.** The index shows the `#define` lines, but I could not read the guards around `library/common.h:132`, so I can't confirm whether that define is unconditional or sits inside a conditional block. I also couldn't check whether `common.h` is included before the public headers in every library file, which determines which translation units actually get the unwrapped names. The index also has no record of the struct's field definitions beyond the `aes.h` lines, so the claim that the macro only renames fields rests on the `private_access.h` macro bodies and the `aes.h` declarations.