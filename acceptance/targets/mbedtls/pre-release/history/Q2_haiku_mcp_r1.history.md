# Q2 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll search the mbedtls index for public structs and macros that define struct members.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"public struct macro member","note":"No matching symbols for 'public struct macro member'. This is NOT an error and NOT a malformed call, and it is NOT a defini…

- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"mbedtls_ssl_context_get_config","kind":"function","file":"include/mbedtls/ssl.h","brief":"Return the SSL configuration structure associated with the given SSL cont…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":5,"results":[{"name":"MBEDTLS_PRIVATE","kind":"macro definition","file":"include/mbedtls/private_access.h","brief":"private_##member"},{"name":"MBEDTLS_PRIVATE_ACCESS_H","kind":"macro d…

- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"data hiding implementation","note":"No matching symbols for 'data hiding implementation'. This is NOT an error and NOT a malformed call, and it is NOT a defini…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/private_access.h
### 6. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** 1	/** 2	 * \file private_access.h 3	 * 4	 * \brief Macro wrapper for struct's members. 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 9	 */ 10	 11	#ifnd…

- **got:** {"subject":"MBEDTLS_PRIVATE","subject_kind":"macro","name":"MBEDTLS_PRIVATE","rowid":6061,"signature":"#define MBEDTLS_PRIVATE(member)","file":"include/mbedtls/private_access.h","line_start":15,"line_end":15,"brief":"","…

### 7. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":3,"found":3,"subject":["mbedtls_pk_ec","mbedtls_pk_rsa","mbedtls_ssl_context"],"results":[{"subject":"mbedtls_pk_ec","subject_kind":"function","name":"mbedtls_pk_ec","rowid":6055,"signature":"s…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/ssl.h
- **got:** 1730	 1731	struct mbedtls_ssl_context { 1732	    const mbedtls_ssl_config *MBEDTLS_PRIVATE(conf); /*!< configuration information          */ 1733	 1734	    /* 1735	     * Miscellaneous 1736	     */ 1737	    int MBEDTLS_P…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/pk.h
- **got:** 600	 *                  a key of the type identified in \p attributes. 601	 *                  Another error code on other failures. 602	 */ 603	int mbedtls_pk_get_psa_attributes(const mbedtls_pk_context *pk, 604	       …

### 10. `Grep`
- **asked:** pattern=struct mbedtls_pk_context|typedef.*mbedtls_pk_context, path=~/ddb-targets/mbedtls/include/mbedtls
- **got ⚠ error:** <tool_use_error>InputValidationError: Grep failed due to the following issue: An unexpected parameter `limit` was provided</tool_use_error>

### 11. `Grep`
- **asked:** pattern=struct mbedtls_pk_context|typedef.*mbedtls_pk_context, path=~/ddb-targets/mbedtls/include/mbedtls
- **got:** ~/ddb-targets/mbedtls/include/mbedtls/pk.h:220:typedef struct mbedtls_pk_context {

### 12. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/pk.h
- **got:** 220	typedef struct mbedtls_pk_context { 221	    /** Method table */ 222	    const mbedtls_pk_info_t *MBEDTLS_PRIVATE(pk_info); 223	    /** Underlying type-specific key context */ 224	    void *MBEDTLS_PRIVATE(pk_ctx); 22…

### 13. `Grep`
- **asked:** pattern=mbedtls_pk_get|mbedtls_ssl_get, path=~/ddb-targets/mbedtls/include/mbedtls/pk.h
- **got:** 433:size_t mbedtls_pk_get_bitlen(const mbedtls_pk_context *ctx); 442:static inline size_t mbedtls_pk_get_len(const mbedtls_pk_context *ctx) 444:    return (mbedtls_pk_get_bitlen(ctx) + 7) / 8; 505: * int ret = mbedtls_pk…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/common.h
- **got:** 125	#endif 126	 127	/** Allow library to access its structs' private members. 128	 * 129	 * Although structs defined in header files are publicly available, 130	 * their members are private and should not be accessed by …

### 15. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/programs/ssl/ssl_client2.c
- **got:** 1	/* 2	 *  SSL client with certificate authentication 3	 * 4	 *  Copyright The Mbed TLS Contributors 5	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 6	 */ 7	 8	#define MBEDTLS_ALLOW_PRIVATE_ACCESS 9	 10	#in…

### 16. `Grep`
- **asked:** pattern=\.private_pk_ctx|\.MBEDTLS_PRIVATE\(pk_ctx\), path=~/ddb-targets/mbedtls
- **got:** ~/ddb-targets/mbedtls/include/mbedtls/pk.h:1048:            return (mbedtls_rsa_context *) (pk).MBEDTLS_PRIVATE(pk_ctx); ~/ddb-targets/mbedtls/include/mbedtls/pk.h:1073:            return (mbedtls_ecp_keypair *) (pk).MBE…

**Reasoning.** ---

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

**The Library** (e.g., `library/common.h:132`, `library/pk_internal.h`) defines `MBEDTLS_ALLOW_PRIVATE_ACCESS`, so `MBEDTLS_PRIVATE(member)` expands to just `member`. Library code accesses

---

## Final answer as submitted

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
