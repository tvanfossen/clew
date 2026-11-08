**What it accomplishes:** `MBEDTLS_PRIVATE(member)` is a preprocessor macro that renames a struct member so that code outside the library can't reach it by name. `include/mbedtls/private_access.h:15` defines it as `private_##member` when `MBEDTLS_ALLOW_PRIVATE_ACCESS` is not defined, and as plain `member` when it is. A consumer who writes `ctx.reseed_counter` gets a compile error because the field is actually called `private_reseed_counter`. The migration guide describes this as the escape hatch: "As a last resort, you can access the field `foo` of a structure `bar` by writing `bar.MBEDTLS_PRIVATE(foo)`" (`docs/3.0-migration-guide.md`, "Most structure fields are now private").

The point is to keep internal state out of the public contract. Many of the wrapped fields carry invariants that outside code can break silently. The MPI sign field is one: `include/mbedtls/bignum.h` says `s` must be +1 for zero, and that `calloc()` or `= {0}` does not create a valid MPI. The CTR-DRBG reseed counter (`ctr_drbg.h`) and the PSA driver-ID fields in `psa/crypto_struct.h` are similar. Hiding them lets the library change layout and bookkeeping without breaking callers, and makes accidental misuse a build failure rather than a runtime bug. Note that this is a compile-time guard, not access control. Any translation unit can define the opt-out macro before including the headers.

**For whom:** the opt-out is for the library's own code and for its bundled programs. Application authors are the ones it is designed to stop.

The gate is `MBEDTLS_ALLOW_PRIVATE_ACCESS`, and the index shows three places it is turned on:

| Where | What it means |
|---|---|
| `library/common.h:132` | The library's internal utility header. Any library source that includes it gets direct field access to every `MBEDTLS_PRIVATE` member. This is the main opt-out. |
| `programs/ssl/ssl_client2.c:8` | The client test program defines it at the top of the file, so the whole file can read and write internals. |
| `programs/ssl/ssl_server2.c:8` | Same for the server test program. |

The index reports the symbol as having no config declaration (`origin: undeclared`). It is not a build option a user sets in `mbedtls_config.h`. It is set by the code itself.

For code in those places, every `MBEDTLS_PRIVATE(x)` expands to `x`, so direct access like `ssl->state` compiles. Everywhere else, the same access fails to build.

**Caveats:**
- The index shows that the `#ifndef` and the `private_##` definition exist, but it does not give me the body of the `#else` branch, so I inferred the plain-`member` expansion from the second macro entry at line 17.
- The index does not record include order. For `library/common.h:132` to take effect on a struct header, that header must be included after `common.h` defines the opt-out, because the expansion happens at the point the struct is declared. I could not verify that order from the index. Check the include chain in `library/` before relying on it.