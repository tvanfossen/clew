**What it does.** `MBEDTLS_PRIVATE(member)` is a macro, defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

Struct declarations in the public headers wrap their fields in it (about 889 occurrences across 74 files, e.g. `ssl.h` has 210). By default every field is therefore named `private_<name>`. Code outside the library that writes `ctx->state` gets a compile error, and code that writes `ctx->MBEDTLS_PRIVATE(state)` compiles to `private_state`. The point is to make the internal layout unavailable to applications, so that Mbed TLS can change fields without breaking callers' source, and to make accidental use of internals visible at the call site. The public header `ssl.h:5162-5169` says direct access is deprecated and may break in any release.

**Who gets the opt-out.** Three places turn it on:

1. **The library itself**: `library/common.h:132` has `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`. That header is internal, not installed under `include/`. The library's `.c` files and internal headers include it (for example `ssl_msg.c`, `ssl_client.c`, `x509.c`, `rsa.c`, and many others), so inside the library every field is accessed by its real name. Since `common.h` comes before the rest of the library's includes in these files, the define takes effect before the public headers are parsed.

2. **Two test/demo programs**: `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` define it as their first line, before `#include "ssl_test_lib.h"`. Those programs read internal state directly. It is a per-translation-unit define, so it only affects those two files.

3. **Nothing else in the public surface.** Applications have to define the macro themselves before including any Mbed TLS header. The documented escape hatch is `bar.MBEDTLS_PRIVATE(foo)` (`docs/3.0-migration-guide.md:74`), which warns that it is unsupported and may break in a minor release.

**What that means for the code in those places.**

- Library code and the two `ssl_*2.c` programs see real field names, so they compile against the struct layout as it stands. Changing a field name in a header breaks them at compile time, not silently.
- `programs/ssl/ssl_context_info.c` does **not** define the opt-out, yet uses `ciphersuite_info->MBEDTLS_PRIVATE(flags)` (lines 553-568). It works because the macro is applied consistently in the declaration and the use, so it resolves to `private_flags` in both places. It is a consumer that reaches into internals through the sanctioned spelling, not through the opt-out.
- Public inline helpers in headers, such as `mbedtls_ssl_is_handshake_over` (`ssl.h:5148`) and `mbedtls_ssl_session_get_id_len` (`ssl.h:2812`), also use `MBEDTLS_PRIVATE(...)`. They compile for external users because the header-declared field names match the macro's expansion.

**Caveat.** I checked the defines and the representative call sites, but I did not verify every library file's include order for `common.h`. The internal header `library/ssl_ciphersuites_internal.h` uses `MBEDTLS_PRIVATE` 8 times, and I did not confirm that every path that includes it has already pulled in `common.h`.