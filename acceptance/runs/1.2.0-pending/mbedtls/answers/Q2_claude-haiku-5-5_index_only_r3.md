**What it does:** `MBEDTLS_PRIVATE(member)` wraps a struct field name in `include/mbedtls/private_access.h:15`. By default it expands to `private_##member`, so a field such as `mbedtls_aes_context::MBEDTLS_PRIVATE(nr)` (`include/mbedtls/aes.h:64`) is declared as `private_nr`. Code that writes `ctx.nr` then fails to compile. The struct layout and the header stay the same, but the names are hidden from ordinary callers. The header is not an encapsulation boundary at runtime; it is a compile-time guard on the field names.

**Who it's for:** application code that includes the public mbedtls headers. The guard tells those users that the fields are internal and may change, and it stops them from depending on them by accident.

**Where the opt-out is turned on:**

- `private_access.h:14-18` gates the macro on `MBEDTLS_ALLOW_PRIVATE_ACCESS`. If the symbol is not defined, `MBEDTLS_PRIVATE` renames the member. If it is defined, the macro expands to the bare member name.
- `library/common.h:132` contains `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`. Library translation units that include `common.h` therefore get the real field names. Inside the library, the wrapper does nothing.
- `programs/ssl/ssl_client2.c:8` and `programs/ssl/ssl_server2.c:8` also define it. These are the sample programs, which read struct internals directly.

**What this means for those places:** the library and the two sample SSL programs can touch fields by name, and the compiler will not catch that. The guard only constrains outside users. Any external code that defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the headers gets the same access, so it is a deliberate escape hatch, not a security boundary.

**Caveats about this index:**

- `programs/ssl/*.c` is not indexed. I know about their `#define` lines only from the macro's gating records, so I did not see their surrounding code.
- I could see the `library/common.h:132` define but not whether it sits inside any `#if`. The index lists no gate on it, so I am treating it as unconditional. Check that line if the distinction matters.