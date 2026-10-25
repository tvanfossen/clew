**What it does.** `MBEDTLS_PRIVATE(member)` is a macro that wraps a struct member name in the declaration. With the opt-out off, it expands to `private_##member` (token-pasting), so the field is renamed. Code outside the library that writes `ctx.member` then fails to compile, and the field is only reachable by the mangled name. With the opt-out on, it expands to plain `member`, so the field is ordinary. The macro is defined in `include/mbedtls/private_access.h` (lines 14–18), and its gate is `MBEDTLS_ALLOW_PRIVATE_ACCESS`. The index does not show the wrapped declarations' bodies here, but the dossier shows the wrapping on members such as `mbedtls_aes_context` (`nr`, `rk`) and `mbedtls_ctr_drbg_context`, and the ~480 `MBEDTLS_PRIVATE` declarator rows in `ssl.h`, `psa/crypto_struct.h`, `bignum.h`, `rsa.h`, and others.

**The intent.** The 3.0 migration guide (`docs/3.0-migration-guide.md`, "Most structure fields are now private") says the fields are not part of the public API. The escape hatch is written as "as a last resort": `bar.MBEDTLS_PRIVATE(foo)`. So the purpose is to keep struct layout and field names out of the supported API. Applications can then change internals across releases without breaking, and the library keeps the freedom to rearrange or rename fields. The opt-out exists so the library's own code and its test tools can still touch those fields.

**Who the opt-out is for.** The index shows the define in three places:

| Site | What it is |
|---|---|
| `library/common.h:132` | `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` (empty body). Per its doc: "Allow library to access its structs' private members." |
| `programs/ssl/ssl_client2.c:8` | Test/debug client program |
| `programs/ssl/ssl_server2.c:8` | Test/debug server program |

So the opt-out is for library-internal code and for two sample/test SSL programs that poke at internals. Those translation units see the real field names, and the macro gate picks the plain-name branch for them. Everything else, including ordinary applications, gets the renamed fields. Where the library's own code is concerned, the define must be visible before `private_access.h` is included, since the `#ifndef` is evaluated there. For the two `programs/ssl` files, line 8 suggests it sits above the includes, but the index does not record include order, so I can't confirm that.

**Gaps.**
- I can't tell whether `library/common.h:132` is unconditional or inside a conditional. Its surrounding lines are not in the index.
- The gate symbol is "origin undeclared": the index has no Kconfig or config header for it, and no config header is recorded for this target. So I can't say whether the default build enables it. The index's `configured_macros` list (`MBEDTLS_THREADING_C`, `MBEDTLS_THREADING_PTHREAD`) is the index build's flags and does not include it.
- Other programs and tests that touch private fields are not visible as opt-ins in this index. The index only shows these three sites define the macro, so if a test in `tests/` accesses fields, it does so either through the library's internal header path or not at all, which I can't tell from here.
- Doxygen's function rows for `MBEDTLS_PRIVATE` (336 "callers") are artifacts of the macro appearing in declarators, not real functions. I'd discount those.