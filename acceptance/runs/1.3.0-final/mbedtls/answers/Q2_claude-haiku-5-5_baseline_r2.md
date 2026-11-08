**What it accomplishes:** `MBEDTLS_PRIVATE(member)` is a rename, not an access control. In `include/mbedtls/private_access.h`, when `MBEDTLS_ALLOW_PRIVATE_ACCESS` is not defined, `MBEDTLS_PRIVATE(member)` expands to `private_##member`. The header declares the struct fields through this macro, so a default consumer's `ctx->MBEDTLS_PRIVATE(state)` refers to `private_state`, and the real name `state` is invisible to it. The effect is that the member names are no longer part of the usable API. Maintainers can rename or reorder them without it counting as a break, and every access to a private field is greppable as `MBEDTLS_PRIVATE(`. The `ssl.h` warning at line 5163 says this directly: direct access is deprecated and "could be broken in any future release."

Because it is a preprocessor rename, nothing stops a determined caller from writing `->MBEDTLS_PRIVATE(x)` without the opt-out. It discourages access and marks it as unsupported; it does not enforce anything.

**For whom:** the opt-out is for the library's own code and for a few internal consumers. It is switched on in these places in this tree:

| Where | How | What it means |
|---|---|---|
| `library/common.h:132` | `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Every library `.c`/`.h` that includes `common.h` (the library translation units, plus several test and fuzz files) sees the real member names. This is the main opt-out. |
| `programs/ssl/ssl_server2.c:8` | define at the top of the file | The example server reads the real fields directly. |
| `programs/ssl/ssl_client2.c:8` | same | Same for the example client. |

I did not check the include order in the two `programs/ssl` files, so I can't confirm the define precedes every mbedtls include there.

Two concrete examples show the split:

- `programs/fuzz/fuzz_dtlsserver.c:138` reads `ssl.MBEDTLS_PRIVATE(next_record_offset)`. It includes `common.h` at line 4, so the opt-out is active and this compiles to the real field. The fuzzer is inside the library's trust boundary and reaches into it on purpose.
- `programs/ssl/ssl_context_info.c:553`, `:557`, `:564` and `:568` use `ciphersuite_info->MBEDTLS_PRIVATE(flags)`, `(cipher)` and `(mac)` with no opt-out. These resolve to the mangled `private_flags`, `private_cipher` and `private_mac`, so this program is a default-mode consumer. It is using the unsupported path, and a rename inside the library would break it without any warning from the compiler's naming rules.

**What this means for the code in those places:** inside the library, the fields are ordinary struct members, so the library can change its own internals freely without breaking itself. Tools and examples that use the opt-out are tied to the internal layout, so they are the first code to break when a field is renamed. Default-mode consumers such as `ssl_context_info.c` are the ones that actually depend on private names, and that dependency is exactly what the macro is meant to make visible.