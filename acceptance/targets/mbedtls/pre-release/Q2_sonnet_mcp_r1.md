# Q2 — mcp — sonnet — run 1

## Answer

**The macro:** `MBEDTLS_PRIVATE`, defined in `include/mbedtls/private_access.h:14-18`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```
(include/mbedtls/private_access.h:14-18)

It's used to wrap struct member declarations everywhere in the public headers — e.g. `include/mbedtls/aes.h:64-90`:
```c
int MBEDTLS_PRIVATE(nr);
uint32_t MBEDTLS_PRIVATE(buf)[44];
mbedtls_aes_context MBEDTLS_PRIVATE(crypt);
```
856 occurrences across 59 headers (confirmed via grep over `include/`), including core types like `mbedtls_pk_ec`, `mbedtls_pk_rsa` (per the index's `referenced_by` for the macro).

**What it expands to, and when:**
- If `MBEDTLS_ALLOW_PRIVATE_ACCESS` is **not** defined at the point the header is included, `MBEDTLS_PRIVATE(member)` → **`private_##member`** (token-pasted, e.g. `MBEDTLS_PRIVATE(nr)` → `private_nr`). This is the default, application-facing behavior.
- If `MBEDTLS_ALLOW_PRIVATE_ACCESS` **is** defined first, `MBEDTLS_PRIVATE(member)` → **`member`** (the macro becomes a no-op).

**Library vs. application view:**
The library itself defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` in `library/common.h:132`, with the comment "Allow library to access its structs' private members" (`library/common.h:127-132`). `common.h` is included before any public headers in library `.c` files, so when the library's own source compiles those headers, every `MBEDTLS_PRIVATE(member)` collapses to the plain `member` name — i.e. the library sees its structs with their real, natural field names (`nr`, `buf`, `crypt`, …).

An application, by contrast, normally does **not** define `MBEDTLS_ALLOW_PRIVATE_ACCESS`, so for it every field is renamed to `private_<member>` — a name the application isn't supposed to write directly. The intent (per the header's own brief, "Macro wrapper for struct's members," `include/mbedtls/private_access.h:4`, and `docs/3.0-migration-guide.md:74`) is that applications go through accessor functions instead of touching struct fields.

**What happens if application code reaches past it:** the migration guide is explicit (`docs/3.0-migration-guide.md:74`): "As a last resort, you can access the field `foo` of a structure `bar` by writing `bar.MBEDTLS_PRIVATE(foo)`. Note that you do so at your own risk, since such code is likely to break in a future minor version of Mbed TLS." Two of the three call sites that pre-define `MBEDTLS_ALLOW_PRIVATE_ACCESS` themselves are the sample programs `programs/ssl/ssl_client2.c:8` and `programs/ssl/ssl_server2.c:8` — i.e. even Mbed TLS's own example applications opt into direct-field access rather than staying purely at the accessor-function API, which the guide flags as unsupported beyond LTS releases (`docs/3.0-migration-guide.md:74`, noting only the 3.6 LTS line tries to keep this stable).

## Gaps
- I did not exhaustively enumerate every one of the 856 `MBEDTLS_PRIVATE` call sites or every accessor-function replacement; `aes.h` and `common.h` were read directly to confirm the pattern the index pointed at (the index's macro `referenced_by` list was partial — only 4 names — so file-level grep was needed to get the real usage count and confirm library/application include ordering, which the index does not model).
- I did not verify at the preprocessor/build level that `common.h` is transitively included before public headers in *every* library `.c` file — this is inferred from the standard mbedtls build convention and the placement/comment of the define, not directly traced edge-by-edge through the index.
