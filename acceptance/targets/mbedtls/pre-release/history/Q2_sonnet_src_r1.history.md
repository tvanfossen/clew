# Q2 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Grep`
- **asked:** pattern=define MBEDTLS_PRIVATE, path=~/ddb-targets/mbedtls
- **got:** ~/ddb-targets/mbedtls/include/mbedtls/private_access.h:12:#define MBEDTLS_PRIVATE_ACCESS_H ~/ddb-targets/mbedtls/include/mbedtls/private_access.h:15:#define MBEDTLS_PRIVATE(member) private_##member ~/ddb-targets/mbedtls/…

### 2. `Grep`
- **asked:** pattern=MBEDTLS_PRIVATE, path=~/ddb-targets/mbedtls
- **got:** Found 50 files limit: 50 ~/ddb-targets/mbedtls/tests/suites/test_suite_x509write.function ~/ddb-targets/mbedtls/tests/suites/test_suite_psa_crypto.function ~/ddb-targets/mbedtls/programs/ssl/ssl_context_info.c ~/ddb-targ…

**Reasoning.** Let me read the full private_access.h header for exact conditional logic and an example usage.

### 3. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/private_access.h
- **got:** 1	/** 2	 * \file private_access.h 3	 * 4	 * \brief Macro wrapper for struct's members. 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 9	 */ 10	 11	#ifnd…

### 4. `Grep`
- **asked:** pattern=MBEDTLS_PRIVATE\(, path=~/ddb-targets/mbedtls/include/mbedtls/gcm.h
- **got:** 60:    mbedtls_block_cipher_context_t MBEDTLS_PRIVATE(block_cipher_ctx);  /*!< The cipher context used. */ 62:    mbedtls_cipher_context_t MBEDTLS_PRIVATE(cipher_ctx);    /*!< The cipher context used. */ 64:    uint64_t …

### 5. `Grep`
- **asked:** pattern=MBEDTLS_ALLOW_PRIVATE_ACCESS, path=~/ddb-targets/mbedtls
- **got:** ~/ddb-targets/mbedtls/library/common.h:132:#define MBEDTLS_ALLOW_PRIVATE_ACCESS ~/ddb-targets/mbedtls/include/mbedtls/ssl.h:5163: *                 defining MBEDTLS_ALLOW_PRIVATE_ACCESS, this is now ~/ddb-targets/mbedtls…

### 6. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/common.h
- **got:** 110	 111	#define ARRAY_LENGTH(array)                                           \ 112	    (STATIC_ASSERT_THEN_RETURN(IS_ARRAY_NOT_POINTER(array),         \ 113	                               ARRAY_LENGTH_UNSAFE(array))) 1…

### 7. `Grep`
- **asked:** pattern=#include, path=~/ddb-targets/mbedtls/library/gcm.c
- **got:** 18:#include "common.h" 22:#include "mbedtls/gcm.h" 23:#include "mbedtls/platform.h" 24:#include "mbedtls/platform_util.h" 25:#include "mbedtls/error.h" 26:#include "mbedtls/constant_time.h" 29:#include "block_cipher_inte…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/ssl.h
- **got:** 5145	 */ 5146	static inline int mbedtls_ssl_is_handshake_over(mbedtls_ssl_context *ssl) 5147	{ 5148	    return ssl->MBEDTLS_PRIVATE(state) >= MBEDTLS_SSL_HANDSHAKE_OVER; 5149	} 5150	 5151	/** 5152	 * \brief          Perf…

### 9. `Grep`
- **asked:** pattern=private_access|MBEDTLS_ALLOW_PRIVATE_ACCESS, path=~/ddb-targets/mbedtls/docs
- **got:** ~/ddb-targets/mbedtls/docs/psa-transition.md:155:| `private_access.h` | N/A | No public APIs (internal support header) |

### 10. `Grep`
- **asked:** pattern=MBEDTLS_PRIVATE|private_access|ALLOW_PRIVATE_ACCESS, path=~/ddb-targets/mbedtls/ChangeLog.d
- **got:** No files found

**Reasoning.** I have enough to answer confidently now.

### 11. `Grep`
- **asked:** pattern=MBEDTLS_PRIVATE\(, path=~/ddb-targets/mbedtls/include/mbedtls/ssl.h
- **got:** ~/ddb-targets/mbedtls/include/mbedtls/ssl.h:209  Found 209 total occurrences across 1 file.

**Reasoning.** ## The macro

`MBEDTLS_PRIVATE(member)`, defined in `include/mbedtls/private_access.h:15-17`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```
(`include/mbedtls/private_access.h:14-18`)

It's a token-paste macro: given `MBEDTLS_PRIVATE(state)`, it expands to either the literal identifier `private_state`, or to plain `state`, depending on whether `MBEDTLS_ALLOW_PRIVATE_ACCESS` is `#define`d *at the point the header is preprocessed*.

Every struct member declaration in the public headers is written

---

## Final answer as submitted

## The macro

`MBEDTLS_PRIVATE(member)`, defined in `include/mbedtls/private_access.h:15-17`:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```
(`include/mbedtls/private_access.h:14-18`)

It's a token-paste macro: given `MBEDTLS_PRIVATE(state)`, it expands to either the literal identifier `private_state`, or to plain `state`, depending on whether `MBEDTLS_ALLOW_PRIVATE_ACCESS` is `#define`d *at the point the header is preprocessed*.

Every struct member declaration in the public headers is written through it, e.g. in `include/mbedtls/gcm.h:60-73`:
```c
mbedtls_block_cipher_context_t MBEDTLS_PRIVATE(block_cipher_ctx);
...
uint64_t MBEDTLS_PRIVATE(len);
```
and pervasively in `include/mbedtls/ssl.h` (209 uses of the macro in that one file). So the struct's *actual* member name at compile time is literally `private_len`/`private_block_cipher_ctx`/etc. unless `MBEDTLS_ALLOW_PRIVATE_ACCESS` was defined before that header was included — there is no second, differently-named field; it's the same declaration renamed by the preprocessor before either the library or the application ever sees it.

## What the library sees vs. what an application sees

`library/common.h:132` unconditionally does:
```c
#define MBEDTLS_ALLOW_PRIVATE_ACCESS
```
and every library `.c` file includes `common.h` before any public header that declares structs — e.g. `library/gcm.c:18` includes `"common.h"` and only then, at `library/gcm.c:22`, `"mbedtls/gcm.h"`. So by the time the library's own headers are parsed, `MBEDTLS_ALLOW_PRIVATE_ACCESS` is already defined, and `MBEDTLS_PRIVATE(state)` expands to plain `state`. The library sees ordinary, unprefixed member names and accesses them directly (e.g. `ssl->MBEDTLS_PRIVATE(state)` in `include/mbedtls/ssl.h:5148` resolves to `ssl->state` inside library code).

An application, by default, does **not** define `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including mbedtls headers. So for it, the same struct's fields are actually named `private_state`, `private_len`, `private_block_cipher_ctx`, etc. — the macro-guarded name, not the "clean" one.

Two sample programs opt back in explicitly by defining the macro before any mbedtls include: `programs/ssl/ssl_server2.c:8` and `programs/ssl/ssl_client2.c:8` both do `#define MBEDTLS_ALLOW_PRIVATE_ACCESS`.

The header comment in `library/common.h:127-131` states the intent directly: "Although structs defined in header files are publicly available, their members are private and should not be accessed by the user."

## What happens if application code reaches past it

If application code writes `ssl->state` directly (without defining `MBEDTLS_ALLOW_PRIVATE_ACCESS`), it fails to compile: the struct has no member named `state`, only `private_state`. This is a compile-time error (`no member named 'state' in 'struct mbedtls_ssl_context'` or equivalent), not a silent behavior change — the rename happens identically for the struct's own declaration and for any external reference, so any code that skips the macro just doesn't type-match the struct anymore.

The documented escape hatches, per `include/mbedtls/ssl.h:5159-5169`, are either accessing via `ssl->MBEDTLS_PRIVATE(state)` (routes through the same macro so it still expands to `private_state`) or defining `MBEDTLS_ALLOW_PRIVATE_ACCESS` before including the headers (as `ssl_server2.c`/`ssl_client2.c` do) — but the same comment explicitly calls this "deprecated" and warns it "could be broken in any future release," i.e. mbedtls reserves the right to move/rename/remove these fields since the naming convention marks them as not part of the stable API.

## Gaps

- I did not find any ChangeLog.d entries describing when `MBEDTLS_PRIVATE`/`private_access.h` was introduced (`ChangeLog.d` had no matches) — only the current header/comment state was inspected, not project history.
- I did not exhaustively verify every one of the ~50 headers using the macro include `common.h` in matching library `.c` files; I spot-checked `gcm.c` as representative of the pattern used throughout `library/`.
