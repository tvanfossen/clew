# Q2 — mcp — haiku — run 1

---

## Answer

The macro is **`MBEDTLS_PRIVATE`**, defined in `include/mbedtls/private_access.h:15`. Here is its exact expansion:

**Default expansion (no MBEDTLS_ALLOW_PRIVATE_ACCESS):**
```c
#define MBEDTLS_PRIVATE(member) private_##member
```

**Alternative expansion (with MBEDTLS_ALLOW_PRIVATE_ACCESS defined):**
```c
#define MBEDTLS_PRIVATE(member) member
```

### What the Library Sees vs. Applications

**The Library** (e.g., `library/common.h:132`, `library/pk_internal.h`) defines `MBEDTLS_ALLOW_PRIVATE_ACCESS`, so `MBEDTLS_PRIVATE(member)` expands to just `member`. Library code accesses struct fields using their original names:

```c
// In library code with MBEDTLS_ALLOW_PRIVATE_ACCESS defined
(pk).MBEDTLS_PRIVATE(pk_ctx)  →  expands to  (pk).pk_ctx
```

**Applications** do NOT define `MBEDTLS_ALLOW_PRIVATE_ACCESS`, so `MBEDTLS_PRIVATE(member)` expands to `private_##member`. Struct members are renamed with a `private_` prefix:

```c
// In application code (no MBEDTLS_ALLOW_PRIVATE_ACCESS)
(pk).MBEDTLS_PRIVATE(pk_ctx)  →  expands to  (pk).private_pk_ctx
```

### Real-World Example

In the public struct `mbedtls_ssl_context` (`include/mbedtls/ssl.h:1731`), declared members appear as:

```c
struct mbedtls_ssl_context {
    const mbedtls_ssl_config *MBEDTLS_PRIVATE(conf);     // Declared name
    int MBEDTLS_PRIVATE(state);                           // Declared name
    // ...
};
```

But the actual field names seen by applications are `private_conf`, `private_state`, etc., as confirmed by the struct members list (all 65+ members begin with `private_`).

### What Happens If Application Code Bypasses It

If application code tries to access the original member name directly:

```c
ctx.conf     // ❌ Compiler error: no member named 'conf'
ctx.pk_ctx   // ❌ Compiler error: no member named 'pk_ctx'
```

The compiler **rejects** the access because the actual member is named `private_conf` or `private_pk_ctx`. Applications must instead use provided accessor functions like `mbedtls_pk_rsa()` (`include/mbedtls/pk.h:1044`), which safely retrieves the internal context via the macro:

```c
static inline mbedtls_rsa_context *mbedtls_pk_rsa(const mbedtls_pk_context pk) {
    switch (mbedtls_pk_get_type(&pk)) {
        case MBEDTLS_PK_RSA:
            return (mbedtls_rsa_context *) (pk).MBEDTLS_PRIVATE(pk_ctx);  // Safe accessor
        // ...
    }
}
```

This design enforces **encapsulation**: struct layouts remain opaque to external code, allowing the library to evolve internals without breaking ABI compatibility.

---

## Gaps

None — the index fully answered the question. All claims are supported by index dossier results and direct file reads.
