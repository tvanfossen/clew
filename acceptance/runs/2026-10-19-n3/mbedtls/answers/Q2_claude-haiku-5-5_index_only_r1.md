**What it does:** `MBEDTLS_PRIVATE(member)` is a preprocessor rename of a struct field. In `include/mbedtls/private_access.h`, when `MBEDTLS_ALLOW_PRIVATE_ACCESS` is not defined, `MBEDTLS_PRIVATE(member)` expands to `private_##member`. When it is defined, it expands to plain `member`. So a field such as `mbedtls_aes_context`'s `nr` is spelled `private_nr` for ordinary users, and any direct use of the public name fails to compile. This is a compile-time barrier against accidental access, not a language-level access control, and the header's own docs describe it only as a "Macro wrapper for struct's members." The index does not show the field layout, so I can't confirm from it that the change is layout-neutral. The rename is the only mechanism it reports.

**For whom:** the wrapping targets *external users of the public headers*. The library's documentation says structs in headers are public, but their members are private and should not be touched by users. The 3.0 migration guide treats direct access as a "last resort" that means writing `bar.MBEDTLS_PRIVATE(foo)` yourself.

**Where the opt-out is turned on in this tree:**

| Location | What it does |
|---|---|
| `library/common.h:132` | Defines `MBEDTLS_ALLOW_PRIVATE_ACCESS`. This is the library's own internal header, so library sources see plain field names. |
| `programs/ssl/ssl_client2.c:8` | Defines it, so this sample client reaches the struct internals directly. |
| `programs/ssl/ssl_server2.c:8` | Same for the sample server. |

For those three places, the field names are plain and the code compiles unchanged. Everyone else gets the `private_` names.

Two caveats from the index. First, it does not show whether the `common.h` define is unconditional or sits behind a guard. Second, it does not show whether `common.h` is always included before `private_access.h` in every library translation unit, which determines whether the library actually gets the opt-out everywhere. Confirming either needs a read of those files, which this index-only session can't do.