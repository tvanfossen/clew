# Q9 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll use the index to identify the public cryptographic interfaces in mbedtls.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"public interface cryptographic operations","note":"No matching symbols for 'public interface cryptographic operations'. This is NOT an error and NOT a malforme…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":3,"results":[{"name":"include/mbedtls/config_adjust_psa_from_legacy.h","kind":"file","file":"include/mbedtls/config_adjust_psa_from_legacy.h","brief":"\\file mbedtls/config_adjust_psa_f…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":25,"results":[{"name":"mbedtls_cipher_check_tag","kind":"function","file":"include/mbedtls/cipher.h","brief":"This function checks the tag for AEAD ciphers. Currently supported with GCM…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":11,"results":[{"name":"psa_cipher_encrypt","kind":"macro definition","file":"tests/include/test/psa_test_wrappers.h","brief":"mbedtls_test_wrap_psa_cipher_encrypt(arg0_key, arg1_alg, ar…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":2,"found":2,"subject":["mbedtls_cipher_crypt","psa_cipher_encrypt"],"results":[{"subject":"mbedtls_cipher_crypt","subject_kind":"function","name":"mbedtls_cipher_crypt","rowid":8443,"signature"…

### 6. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"prose matches","count":2,"results":[{"file_path":"include/mbedtls/config_adjust_psa_from_legacy.h","heading":"include/mbedtls/config_adjust_psa_from_legacy.h — file-level documentation","snippet":"…construct >>P…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/architecture/psa-migration/strategy.md
- **got:** 1	This document explains the strategy that was used so far in starting the 2	migration to PSA Crypto and mentions future perspectives and open questions. 3	 4	Goals 5	===== 6	 7	Several benefits are expected from migrati…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/cipher.h
- **got:** 1	/** 2	 * \file cipher.h 3	 * 4	 * \brief This file contains an abstraction interface for use with the cipher 5	 * primitives provided by the library. It provides a common interface to all of 6	 * the available cipher o…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/psa/crypto.h
- **got:** 4700	 *                              algorithm and key: 4701	 *                              - The required signature size is 4702	 *                                #PSA_SIGN_OUTPUT_SIZE(\c key_type, \c 4703	 *          …

### 10. `Bash`
- **asked:** command=grep -n "psa_cipher_encrypt\|psa_cipher_decrypt\|psa_cipher_operation" ~/ddb-targets/mbedtls/include/psa/crypto.h | head -30
- **got:** 1598: * #psa_cipher_operation_t object to provide other forms of IV. 1633:psa_status_t psa_cipher_encrypt(mbedtls_svc_key_id_t key, 1680:psa_status_t psa_cipher_decrypt(mbedtls_svc_key_id_t key, 1694: *   psa_cipher_oper…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/psa/crypto.h
- **got:** 1590	/** \defgroup cipher Symmetric ciphers 1591	 * @{ 1592	 */ 1593	 1594	/** Encrypt a message using a symmetric cipher. 1595	 * 1596	 * This function encrypts a message with a random IV (initialization 1597	 * vector)…

### 12. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"prose matches","count":10,"results":[{"file_path":"docs/use-psa-crypto.md","heading":"PSA-based operations in the Cipher layer","snippet":"There is a >>new<< API function `mbedtls_cipher_setup_>>psa<<()` to set …

### 13. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/use-psa-crypto.md
- **got:** 1	This document describes the compile-time configuration option 2	`MBEDTLS_USE_PSA_CRYPTO` from a user's perspective. 3	 4	This option: 5	- makes the X.509 and TLS libraries use PSA for cryptographic operations as 6	  mu…

**Reasoning.** Now let me look for any documentation that explicitly contrasts these two interfaces:

### 14. `Bash`
- **asked:** command=grep -r "mbedtls_cipher\|psa_cipher" ~/ddb-targets/mbedtls/docs --include="*.md" | grep -i "legacy\|new\|deprecated\|recommend" | head -20
- **got:** ~/ddb-targets/mbedtls/docs/use-psa-crypto.md:There is a new API function `mbedtls_cipher_setup_psa()` to set up a context ~/ddb-targets/mbedtls/docs/use-psa-crypto.md:and it is recommended to use `psa_cipher_xxx()` or `p…

**Reasoning.** Based on my index queries and source examination, I've identified the two public cryptographic interfaces in mbedtls:

## The Two Public Interfaces

**1. Legacy Cipher API:** `mbedtls_cipher_*` functions
- Located in: `include/mbedtls/cipher.h`
- Functions like: `mbedtls_cipher_crypt()`, `mbedtls_cipher_update()`, `mbedtls_cipher_finish()`, etc.
- Context type: `mbedtls_cipher_context_t`

**2. PSA (Platform Security Architecture) Cipher API:** `psa_cipher_*` functions  
- Located in: `include/psa/crypto.h`
- Functions like: `psa_cipher_encrypt()`, `psa_cipher_decrypt()`, `psa_cipher_encrypt_se

---

## Final answer as submitted

Based on my index queries and source examination, I've identified the two public cryptographic interfaces in mbedtls:

## The Two Public Interfaces

**1. Legacy Cipher API:** `mbedtls_cipher_*` functions
- Located in: `include/mbedtls/cipher.h`
- Functions like: `mbedtls_cipher_crypt()`, `mbedtls_cipher_update()`, `mbedtls_cipher_finish()`, etc.
- Context type: `mbedtls_cipher_context_t`

**2. PSA (Platform Security Architecture) Cipher API:** `psa_cipher_*` functions  
- Located in: `include/psa/crypto.h`
- Functions like: `psa_cipher_encrypt()`, `psa_cipher_decrypt()`, `psa_cipher_encrypt_setup()`, `psa_cipher_update()`, `psa_cipher_finish()`, etc.
- Context type: `psa_cipher_operation_t`

## How They Relate

The legacy API acts as a **wrapper/abstraction layer** over the PSA API:

1. **When `MBEDTLS_USE_PSA_CRYPTO` is enabled**, the legacy `mbedtls_cipher_crypt()` function at `library/cipher.c:1335-1427` internally delegates to PSA functions. The code checks `if (ctx->psa_enabled == 1)` and then calls:
   - `psa_cipher_encrypt_setup()` / `psa_cipher_decrypt_setup()`
   - `psa_cipher_set_iv()` 
   - `psa_cipher_update()`
   - `psa_cipher_finish()`

2. **Without PSA enabled**, it uses the legacy implementation path.

This implements what the architecture documentation calls the **"silently call to PSA from the abstraction layer"** strategy — found at `docs/architecture/psa-migration/strategy.md:142-157`.

## Recommendation for New Callers

**New callers should write against the PSA API (`psa_cipher_*` functions).**

The rationale from `docs/use-psa-crypto.md:117-124`:
> "There is a new API function `mbedtls_cipher_setup_psa()` to set up a context that will call PSA to store the key and perform the operations. This function only worked for a small number of ciphers. **It is now deprecated and it is recommended to use `psa_cipher_xxx()` or `psa_aead_xxx()` functions directly instead.**"

## Why PSA for New Code

1. **Future-proof**: The project is migrating away from the legacy API toward PSA as the unified cryptographic interface (Goal G4 in `docs/architecture/psa-migration/strategy.md:12`)
2. **Driver support**: PSA Crypto has better support for hardware drivers and key isolation
3. **Cleaner API**: The PSA API better distinguishes operation types (AEAD vs. unauthenticated ciphers) than the legacy layer's unified context

## Repository Evidence

- Legacy interface definition: `include/mbedtls/cipher.h:1-300` (abstraction for symmetric ciphers)
- PSA interface definition: `include/psa/crypto.h:1590-2000` (symmetric cipher operations)
- Legacy→PSA delegation implementation: `library/cipher.c:1335-1427` (the `mbedtls_cipher_crypt()` function)
- Migration strategy document: `docs/architecture/psa-migration/strategy.md`
- Usage guide: `docs/use-psa-crypto.md`

## Gaps

None identified. The index and source files clearly document both interfaces, their relationship, and the recommended path forward for new callers.
