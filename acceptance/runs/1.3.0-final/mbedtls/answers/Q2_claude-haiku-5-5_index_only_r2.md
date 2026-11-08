**What it does.** `include/mbedtls/private_access.h` defines `MBEDTLS_PRIVATE(member)`. In the default configuration it expands to `private_##member`, so `ctx->MBEDTLS_PRIVATE(state)` compiles to `ctx->private_state`. Public-header struct members are wrapped this way, and the rename makes direct access fail to compile. The index shows the wrapping across the public API. For example, `mbedtls_ssl_is_handshake_over` reads `ssl->MBEDTLS_PRIVATE(state)`, and `psa_set_key_type` writes `attributes->MBEDTLS_PRIVATE(type)`. The effect is that application code must go through the accessor functions (`mbedtls_ssl_get_version_number`, `psa_get_key_type`, and so on), which leaves the library free to change the struct layout without breaking callers. The header's own file doc, "Macro wrapper for struct's members," and the migration docs' note that it has "No public APIs" fit this reading.

**Who the opt-out is for.** The switch is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. When it is defined, the wrapper expands to the plain member name. The index has three definition sites:

| Site | What it is | Effect |
|---|---|---|
| `library/common.h:132` | the library's internal utility header | library translation units that include it see real member names |
| `programs/ssl/ssl_client2.c:8` | test/demo client | direct member access compiles |
| `programs/ssl/ssl_server2.c:8` | test/demo server | direct member access compiles |

The index records no config symbol for it (origin "undeclared", no Kconfig), so it is a plain compile-time define, not a `mbedtls_config.h` option. Nothing else in the tree defines it. Application code in the wild never gets it unless it defines the macro itself before including mbedtls headers.

**What that means for those places.**
- In the library, the inline accessors in public headers (`ssl.h`, `ssl_ciphersuites.h`, `x509_crt.h`, `psa/crypto_struct.h`) compile against real member names. Library code can touch fields directly, so renaming or reordering a field breaks the library build there, not just user code.
- In the two ssl sample programs, the programs read and write struct internals directly. Those are the only consumers that depend on the internal layout. A field change breaks them at compile time, which is the intent, since they are not a supported API.
- The opt-out is compile-time only. It is not an access control. Anyone who defines the macro gets the same access as the library.

**Caveats I could not settle from the index.** The index gives me the line numbers and gate spans but not the verbatim text. I inferred the `#ifndef`/`#else` structure from the gate spans (lines 14–18). I also could not confirm whether the `ssl_*.c` defines sit before or after the mbedtls includes. If they sit after, they would have no effect on the headers they're meant to affect. A quick look at those lines would settle it.