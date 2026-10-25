**What it does.** `MBEDTLS_PRIVATE(member)` is a function-like macro in `include/mbedtls/private_access.h`. In a default build it expands to `private_##member`, so a struct field is declared as, say, `private_nr` instead of `nr` (`aes.h:64`, `mbedtls_aes_context`). Any code outside the library that writes `ctx->nr` therefore fails to compile. The field is still there, and the library's own code reaches it through the same macro, so the rename costs nothing internally. The aim is encapsulation: mbedtls can change struct layouts and field meanings across releases without breaking callers who only used the public API.

**The switch.** `private_access.h` has two arms gated on `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

```
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
  #define MBEDTLS_PRIVATE(member) private_##member   // line 15: hidden names
#endif
#ifdef  MBEDTLS_ALLOW_PRIVATE_ACCESS
  #define MBEDTLS_PRIVATE(member) member             // line 17: plain names
#endif
```

**Who opts out in this tree.** The index records three definition sites for `MBEDTLS_ALLOW_PRIVATE_ACCESS`:

| Site | Who it affects |
|---|---|
| `library/common.h:132` | Library translation units that include the common header. Their `ctx->MBEDTLS_PRIVATE(x)` becomes `ctx->x`, so they see the real field names. |
| `programs/ssl/ssl_client2.c:8` | The sample client program only. It can touch private fields. |
| `programs/ssl/ssl_server2.c:8` | The sample server program only. Same effect. |

Consequences:
- Inside the library, the macro is a no-op. Library code can read and write any field directly.
- The two SSL sample programs are the only application code in the tree that bypasses encapsulation. Their define is the sanctioned exception, presumably so the test tools can inspect state. Any other application or third-party code that defines it gets the same access, and any code that doesn't define it gets compile errors on private fields.
- Opt-out is a per-translation-unit preprocessor define, not a config option. It must appear before the mbedtls headers are included, or the macro has already been expanded.

**Limits of what I could confirm from the index.** I could not read `library/common.h:132` and the `ssl_*.c` lines, so I can't say whether those defines are unconditional or sit inside a conditional. The `origin: undeclared` tag means no config header declares the macro. I also couldn't confirm which library files include `common.h`, so "all library code" is an inference from the header's location. A direct read of those three lines would settle both points.