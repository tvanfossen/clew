**What it does.** `MBEDTLS_PRIVATE(member)` is a rename, not access control. In `include/mbedtls/private_access.h:14-18`, when `MBEDTLS_ALLOW_PRIVATE_ACCESS` is not defined, `MBEDTLS_PRIVATE(foo)` expands to `private_foo`. When it is defined, it expands to `foo`. Public headers write `MBEDTLS_PRIVATE(...)` in the struct declarations (for example `ssl.h:1247-1291`), so a default build compiles those members as `private_*`. Code outside the library that writes `s->foo` then fails to compile, and the migration guide says so: "Attempting to access a private field directly will result in a compilation error" (`docs/3.0-migration-guide.md:68`).

C has no member-level access control, so this is a convention enforced by the name. Anyone who defines the macro before including the headers gets the real names back. The guide calls that route "a last resort… at your own risk" (line 74), and the `ssl.h:5159-5169` warning calls it deprecated and possibly broken in any release.

**Who it is for.** The purpose is to keep the struct layout out of the public ABI/API, so Mbed TLS can add, reorder or retype fields in minor releases (migration guide lines 64, 70). The people it protects are downstream users. It is not a security boundary.

**Where the opt-out is turned on:**

| Where | How it is enabled | What it means there |
|---|---|---|
| `library/common.h:132` | `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`, unconditionally | Every library `.c` that includes `common.h` before a public header gets real member names. Files that use it include `ecdh.c`, `md.c`, `x509_crt.c`, `pk_internal.h`, `ssl_ciphersuites_internal.h`, and most of `library/`. The library is exempt by design. |
| `programs/ssl/ssl_server2.c:8`, `programs/ssl/ssl_client2.c:8` | Defined at the top of the file, before any include | These diagnostic/test programs read internal SSL state directly. |
| `programs/ssl/ssl_context_info.c`, `programs/fuzz/fuzz_dtlsserver.c` | Not defined | These use `MBEDTLS_PRIVATE(...)` spelling and compile against the renamed members, so they are on the public side of the boundary. `fuzz_dtlsserver.c` includes `common.h` first, so it gets the opt-out through that include. `ssl_context_info.c` does not include `common.h` and stays on the public side. |

**What this means for code in those places:**

- **Library code** can touch any field. The define takes effect for that translation unit only. Inside `common.h`'s include chain, public headers are declared with the real names, so library code and headers agree.
- **Ordering matters.** If a `.c` includes a public header before `common.h`, that header's struct is declared as `private_foo`. Later library code that writes `foo` then fails to compile. I inferred this from the macro definition. I did not reproduce it.
- **The two programs** can read internals, so they break if the layout changes. Their fields are not part of the supported API.
- **External code** using the macro without defining the opt-out gets the stated protection. If it defines the macro, it has opted out of the guarantee.

I did not verify two details. `tests/suites/test_suite_x509write.function` uses `MBEDTLS_PRIVATE(extensions)` but does not define the opt-out itself, so it depends on an include. `test_suite_psa_crypto.function` gets it through `common.h` at line 7.