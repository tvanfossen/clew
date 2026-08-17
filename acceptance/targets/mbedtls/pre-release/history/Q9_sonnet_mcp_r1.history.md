# Q9 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"indexed files","count":0,"results":[],"subject":"psa_crypto","note":"No indexed file matches 'psa_crypto'. This corpus holds INDEXED SOURCE FILES only, so a build script, a Doxyfile, a data file or anything else…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"AES public interface","note":"No matching symbols for 'AES public interface'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negativ…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"indexed files","count":0,"results":[],"subject":"include/psa","note":"No indexed file matches 'include/psa'. This corpus holds INDEXED SOURCE FILES only, so a build script, a Doxyfile, a data file or anything el…

### 4. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"mbedtls_aes_crypt_ecb","kind":"function","file":"include/mbedtls/aes.h","brief":"This function performs an AES single-block encryption or decryption operation."}],…

### 5. `mcp__doxyguard-db__search`
- **asked:** text
- **got:** {"kind":"matching symbols","count":11,"results":[{"name":"psa_cipher_encrypt","kind":"macro definition","file":"tests/include/test/psa_test_wrappers.h","brief":"mbedtls_test_wrap_psa_cipher_encrypt(arg0_key, arg1_alg, ar…

### 6. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"indexed files","count":0,"results":[],"subject":"files","note":"No indexed file matches 'files'. This corpus holds INDEXED SOURCE FILES only, so a build script, a Doxyfile, a data file or anything else the index…

**Reasoning.** Confirmed: two public interfaces exist — legacy `mbedtls_*` module API (e.g. `include/mbedtls/aes.h`) and the PSA Crypto API (`include/psa/crypto.h`), with `library/psa_crypto_cipher.c` implementing the PSA layer partly by calling into the legacy drivers. Let me get details on both, plus how PSA relates/wraps the legacy layer, and the actual guidance in the repo docs.

### 7. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"kind":"dossiers","count":3,"found":3,"subject":["mbedtls_psa_cipher_encrypt","psa_cipher_encrypt","mbedtls_aes_crypt_ecb"],"results":[{"subject":"mbedtls_psa_cipher_encrypt","subject_kind":"function","name":"mbedtls_ps…

### 8. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"prose matches","count":19,"results":[{"file_path":"docs/architecture/psa-migration/psa-legacy-bridges.md","heading":"Context","snippet":"Mbed TLS 3.x supports two cryptographic APIs: * The >>legacy<< >>API<< `mb…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/psa-transition.md
- **got:** 1	# Transitioning to the PSA API 2	 3	> I have code written for `mbedtls_` cryptography APIs. How do I migrate to `psa_` APIs? 4	 5	## Introduction 6	 7	Mbed TLS is gradually moving from legacy `mbedtls_xxx` APIs to newe…

### 10. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/architecture/psa-migration/psa-legacy-bridges.md
- **got:** 1	Bridges between legacy and PSA crypto APIs 2	========================================== 3	 4	## Introduction 5	 6	### Goal of this document 7	 8	This document explores the needs of applications that use both Mbed TLS l…

**Reasoning.** ## Two public crypto interfaces in mbedtls

**1. Legacy `mbedtls_xxx` API** — module-per-algorithm, direct-buffer style. Example: `mbedtls_aes_crypt_ecb()`, `include/mbedtls/aes.h` (declared), implemented `library/aes.c:1024-1065`. Callers manage contexts (`mbedtls_aes_context`), key setup, and (for other primitives) their own RNG context directly. Inherited from PolarSSL (`docs/architecture/psa-migration/psa-legacy-bridges.md:22`).

**2. PSA Crypto API `psa_xxx`** — single header `include/psa/crypto.h`, opaque key-handle model. Example: `psa_cipher_encrypt()`, declared `include/psa/crypto.h:4

---

## Final answer as submitted

## Two public crypto interfaces in mbedtls

**1. Legacy `mbedtls_xxx` API** — module-per-algorithm, direct-buffer style. Example: `mbedtls_aes_crypt_ecb()`, `include/mbedtls/aes.h` (declared), implemented `library/aes.c:1024-1065`. Callers manage contexts (`mbedtls_aes_context`), key setup, and (for other primitives) their own RNG context directly. Inherited from PolarSSL (`docs/architecture/psa-migration/psa-legacy-bridges.md:22`).

**2. PSA Crypto API `psa_xxx`** — single header `include/psa/crypto.h`, opaque key-handle model. Example: `psa_cipher_encrypt()`, declared `include/psa/crypto.h:4728`, defined `library/psa_crypto.c:4730-4803`. Introduced in Mbed TLS 2.17 (`docs/architecture/psa-migration/psa-legacy-bridges.md:23`).

## How they relate

They are not independent — PSA is largely built as a wrapper/driver layer over (or alongside) the same primitives:
- `psa_cipher_encrypt` (`library/psa_crypto.c:4730`) locks a key slot, then dispatches through `psa_driver_wrapper_cipher_encrypt` → the transparent "builtin" driver entry point `mbedtls_psa_cipher_encrypt` (`library/psa_crypto_cipher.c:623-679`), which internally sequences `mbedtls_psa_cipher_encrypt_setup` / `_set_iv` / `_update` / `_finish` — the PSA driver-shaped wrapper around the legacy primitive machinery, gated by `MBEDTLS_PSA_BUILTIN_CIPHER` (`library/psa_crypto_cipher.c:278`).
- The `MBEDTLS_USE_PSA_CRYPTO` config option makes the legacy-facing PK/X.509/TLS modules call PSA under the hood instead of legacy primitives directly (`docs/psa-transition.md:53`).
- The relationship and its limits are documented as a deliberate "bridge" design, with an explicit migration timeline: PSA became default-available in 2.18.0 (2019), TLS 1.3 required it from 3.1.0, and **TF-PSA-Crypto 1.0.0 / Mbed TLS 4.0.0 (Oct 2025) removed most legacy crypto APIs**, with 5.0.0 slated to remove the rest (`docs/psa-transition.md:41-45`).

## Which to write against

**PSA (`psa_xxx`), via `#include <psa/crypto.h>`** (`docs/psa-transition.md:59-62`). The repo's own migration guide gives the reasons directly (`docs/psa-transition.md:33-37`):
- Opaque operations support hardware acceleration / secure-element and HSM-resident keys, which the legacy transparent-context API cannot.
- PSA has consistent, checked buffer-size conventions; many legacy functions require the caller to precompute output sizes.
- PSA maintains an internal RNG, removing the legacy pattern of threading an `mbedtls_entropy_context`/DRBG context through every call.
- Most importantly: legacy crypto APIs are already being removed upstream (mostly gone as of the documented 4.0.0 release), so new code written against `mbedtls_xxx` is targeting a shrinking, soon-unsupported surface.

The legacy API's only remaining legitimate use is functionality PSA doesn't yet expose (e.g. `mbedtls/nist_kw.h`, `mbedtls/pk.h`, `mbedtls/asn1.h` — `docs/psa-transition.md:64`), not general-purpose crypto operations like cipher/hash/AEAD, which both APIs cover.

## Where I found this

- Confirmed via index (`dossier`/`search`, mcp__doxyguard-db) on: `mbedtls_aes_crypt_ecb`, `mbedtls_psa_cipher_encrypt`, `psa_cipher_encrypt` — signatures, files, call edges (`psa_cipher_encrypt` → `psa_driver_wrapper_cipher_encrypt` → `mbedtls_psa_cipher_encrypt`), and config gates.
- Confirmed the intent/relationship/recommendation via prose search + direct read of `docs/psa-transition.md` and `docs/architecture/psa-migration/psa-legacy-bridges.md` — these are the repo's own design/migration docs and settle the "which to use" question authoritatively rather than by inference from code alone.

## Gaps

- I did not trace every algorithm family (hash, MAC, AEAD, asymmetric) through the driver-wrapper layer — only cipher/AES, as a representative example. The wrapper pattern (`psa_driver_wrapper_*` → `mbedtls_psa_*_builtin`) is described in the docs as general across mechanisms, but I did not verify each one individually in the index.
- `docs/architecture/psa-migration/psa-legacy-bridges.md` (a design doc, not user guide) has `[TODO]`/`[OPEN]` markers on some asymmetric-crypto specifics (e.g., `mbedtls_pk_sign_ext`/`verify_ext`) — those gaps are the repo's own, not mine, but worth flagging since they bear on completeness of the PSA surface for asymmetric ops.
