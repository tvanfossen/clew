# Q2 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, text
### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":5,"results":[{"name":"MBEDTLS_PRIVATE","kind":"macro definition","file":"include/mbedtls/private_access.h","brief":"private_##member"},{"name":"MBEDTLS_PRIVATE_ACCESS_H","kind":"macro d…

- **got:** {"kind":"prose matches","count":2,"results":[{"file_path":"include/mbedtls/private_access.h","heading":"include/mbedtls/private_access.h — file-level documentation","snippet":"include/>>mbedtls/private<<_access.h \\file …

### 3. `mcp__doxyguard-db__dossier`
- **asked:** kind=macro definition
- **got:** {"subject":"MBEDTLS_PRIVATE","subject_kind":"macro","name":"MBEDTLS_PRIVATE","rowid":6061,"signature":"#define MBEDTLS_PRIVATE(member)","file":"include/mbedtls/private_access.h","line_start":15,"line_end":15,"brief":"","…

### 4. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/private_access.h
- **got:** 1	/** 2	 * \file private_access.h 3	 * 4	 * \brief Macro wrapper for struct's members. 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 9	 */ 10	 11	#ifnd…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/common.h
- **got:** 120	 121	#if defined(__has_builtin) 122	#define MBEDTLS_HAS_BUILTIN(x) __has_builtin(x) 123	#else 124	#define MBEDTLS_HAS_BUILTIN(x) 0 125	#endif 126	 127	/** Allow library to access its structs' private members. 128	 * …

### 6. `Grep`
- **asked:** pattern=MBEDTLS_PRIVATE\(, path=~/ddb-targets/mbedtls/include
- **got:** ~/ddb-targets/mbedtls/include/mbedtls/bignum.h:3 ~/ddb-targets/mbedtls/include/mbedtls/threading.h:2 ~/ddb-targets/mbedtls/include/mbedtls/sha512.h:4 ~/ddb-targets/mbedtls/include/mbedtls/ctr_drbg.h:10 ~/ddb-targets/mbed…

### 7. `Grep`
- **asked:** pattern=MBEDTLS_PRIVATE\(, path=~/ddb-targets/mbedtls/include/mbedtls/aes.h
- **got:** 64:    int MBEDTLS_PRIVATE(nr);                     /*!< The number of rounds. */ 65:    size_t MBEDTLS_PRIVATE(rk_offset);           /*!< The offset in array elements to AES 68:    uint32_t MBEDTLS_PRIVATE(buf)[44];    …

### 8. `Grep`
- **asked:** pattern=#include \"mbedtls/private_access.h\", path=~/ddb-targets/mbedtls/include/mbedtls/aes.h
- **got:** 30:#include "mbedtls/private_access.h"

**Reasoning.** Now I have everything needed. Let me check the migration guide for the "reach past it" consequence detail.

### 9. `Grep`
- **asked:** pattern=MBEDTLS_ALLOW_PRIVATE_ACCESS|MBEDTLS_PRIVATE, path=~/ddb-targets/mbedtls/docs/3.0-migration-guide.md
- **got:** 71- 72-If no accessor function exists, please open an [enhancement request against Mbed TLS](https://github.com/Mbed-TLS/mbedtls/issues/new?template=feature_request.md) and describe your use case. The Mbed TLS developmen…

**Reasoning.** ## Answer

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
856 occurrences across 59 headers (confirmed via grep over `include/`), including c

---

## Final answer as submitted

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
