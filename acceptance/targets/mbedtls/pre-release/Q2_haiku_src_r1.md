# Q2 — src — haiku — run 1

## Answer

The macro is **`MBEDTLS_PRIVATE(member)`**, defined in `include/mbedtls/private_access.h:15` and `include/mbedtls/private_access.h:17`.

### What It Expands To

**Line 14-18 of include/mbedtls/private_access.h:**
```
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

The macro expands **conditionally**:
- **Without** `MBEDTLS_ALLOW_PRIVATE_ACCESS`: Expands to `private_<member>` (prepends `private_`)
- **With** `MBEDTLS_ALLOW_PRIVATE_ACCESS`: Expands to the bare member name

### The Two Worlds

**LIBRARY SEES (with access):**
The library itself defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` at `library/common.h:132`, so:
- A struct like `mbedtls_mpi` with `MBEDTLS_PRIVATE(p)` expands to member `p`
- The library can access `mpi->p`, `mpi->s`, `mpi->n` directly
- Example: `include/mbedtls/bignum.h:213` — `mbedtls_mpi_uint *MBEDTLS_PRIVATE(p)` becomes `mbedtls_mpi_uint *p` inside the library

**APPLICATION SEES (blocked access):**
An application that does NOT define `MBEDTLS_ALLOW_PRIVATE_ACCESS` sees:
- The same struct members renamed with `private_` prefix
- A struct member `MBEDTLS_PRIVATE(p)` expands to `private_p` (not `p`)
- Accessing `mpi->p` produces a **compiler error**: "no member named 'p' in struct"
- The member exists as `mpi->private_p`, but that's a different name

### What Happens if App Code Reaches Past It

An application that tries to access the real member **without wrapping it in the macro or defining `MBEDTLS_ALLOW_PRIVATE_ACCESS`**:

1. **Direct access fails:** `mpi->s = 1;` → Compiler error: field `s` does not exist in struct (the field is now named `private_s`)
2. **Forced access via the "private_" name:** `mpi->private_s = 1;` → Compiles and runs, but accesses a *different struct layout* than intended (the entire struct offset changes when every member is renamed)

The library's documented discouraged workaround (`include/mbedtls/ssl.h:5163-5170`) allows applications to use `ssl->MBEDTLS_PRIVATE(state)` in their code — this invokes the macro in application context, which still expands to `private_state`, making the application read the oddly-named members. This pattern is **deprecated** as of recent versions and is mentioned as something that "could be broken in any future release."

### Citation Examples

- **Macro definition:** `include/mbedtls/private_access.h:15,17`
- **Library enabling access:** `library/common.h:132` — `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`
- **Test/demo programs enabling access:** `programs/ssl/ssl_client2.c:8` — `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` (at top of file before includes)
- **Concrete struct using the macro:** `include/mbedtls/bignum.h:208-229` — `struct mbedtls_mpi` with `MBEDTLS_PRIVATE(p)`, `MBEDTLS_PRIVATE(s)`, `MBEDTLS_PRIVATE(n)`
- **Another example:** `include/mbedtls/ssl.h:1275-1373` — `struct mbedtls_ssl_session` with many `MBEDTLS_PRIVATE()` wrapped members

## Gaps

None identified. The behavior is fully documented in the macro definition file, the library's use of it is visible in `library/common.h`, and the deprecation notice in the public headers explicitly describes the intended and discouraged usage patterns.
