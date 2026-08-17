# Q9 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll analyze the mbedtls repository to identify multiple public interfaces for the same cryptographic operations.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/mbedtls -type f -name "*.h" | grep -E "^~/ddb-targets/mbedtls/include" | head -20
- **got:** ~/ddb-targets/mbedtls/include/psa/crypto_driver_contexts_primitives.h ~/ddb-targets/mbedtls/include/psa/build_info.h ~/ddb-targets/mbedtls/include/psa/crypto_extra.h ~/ddb-targets/mbedtls/include/psa/crypto_compat.h ~/dd…

### 2. `Bash`
- **asked:** command=ls ~/ddb-targets/mbedtls/include/mbedtls/ | head -30
- **got:** aes.h aria.h asn1.h asn1write.h base64.h bignum.h block_cipher.h build_info.h camellia.h ccm.h chacha20.h chachapoly.h check_config.h cipher.h cmac.h compat-2.x.h config_adjust_legacy_crypto.h config_adjust_legacy_from_p…

### 3. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/aes.h
- **got:** 1	/** 2	 * \file aes.h 3	 * 4	 * \brief   This file contains AES definitions and functions. 5	 * 6	 *          The Advanced Encryption Standard (AES) specifies a FIPS-approved 7	 *          cryptographic algorithm that c…

### 4. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/aes.h
- **got:** 60	/** 61	 * \brief The AES context-type definition. 62	 */ 63	typedef struct mbedtls_aes_context { 64	    int MBEDTLS_PRIVATE(nr);                     /*!< The number of rounds. */ 65	    size_t MBEDTLS_PRIVATE(rk_offse…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/psa/crypto.h
- **got:** 1	/** 2	 * \file psa/crypto.h 3	 * \brief Platform Security Architecture cryptography module 4	 */ 5	/* 6	 *  Copyright The Mbed TLS Contributors 7	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later 8	 */ 9	 10	…

### 6. `Bash`
- **asked:** command=grep -n "psa_cipher_encrypt\|psa_cipher_decrypt" ~/ddb-targets/mbedtls/include/psa/crypto.h | head -20
- **got:** 1633:psa_status_t psa_cipher_encrypt(mbedtls_svc_key_id_t key, 1680:psa_status_t psa_cipher_decrypt(mbedtls_svc_key_id_t key, 1737: * -# Call psa_cipher_encrypt_setup() to specify the algorithm and key. 1746: * If an err…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/psa/crypto.h
- **got:** 1630	 *         It is implementation-dependent whether a failure to initialize 1631	 *         results in this error code. 1632	 */ 1633	psa_status_t psa_cipher_encrypt(mbedtls_svc_key_id_t key, 1634	                    …

### 8. `Bash`
- **asked:** command=find ~/ddb-targets/mbedtls -type f \( -name "*.md" -o -name "*.txt" -o -name "*.rst" \) | xargs grep -l "legacy\|PSA\|interface" 2>/dev/null | head -10
- **got:** ~/ddb-targets/mbedtls/docs/3.0-migration-guide.md ~/ddb-targets/mbedtls/docs/proposed/psa-driver-developer-guide.md ~/ddb-targets/mbedtls/docs/proposed/psa-driver-interface.md ~/ddb-targets/mbedtls/docs/proposed/psa-driv…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/use-psa-crypto.md
- **got:** 1	This document describes the compile-time configuration option 2	`MBEDTLS_USE_PSA_CRYPTO` from a user's perspective. 3	 4	This option: 5	- makes the X.509 and TLS libraries use PSA for cryptographic operations as 6	  mu…

### 10. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/3.0-migration-guide.md
- **got:** 1	# Migrating from Mbed TLS 2.x to Mbed TLS 3.0 2	 3	This guide details the steps required to migrate from Mbed TLS version 2.x to 4	Mbed TLS version 3.0 or greater. Unlike normal releases, Mbed TLS 3.0 breaks 5	compatib…

### 11. `Bash`
- **asked:** command=grep -n "PSA\|legacy\|interface" ~/ddb-targets/mbedtls/docs/3.0-migration-guide.md | head -30
- **got:** 110:This feature was only used in some classic (non-PSA) cryptography modules. It was 111:not used in X.509, TLS or in PSA crypto, and it was not implemented in all 142:RNG interfaces with `mbedtls_entropy_add_source()` …

### 12. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/docs/3.0-migration-guide.md
- **got:** 620	 621	If you used to rely on this module in order to store your private keys 622	securely, please have a look at the key management facilities provided by the 623	PSA crypto API. If you have a use case that's not cove…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/cipher.h
- **got:** 1	/** 2	 * \file cipher.h 3	 * 4	 * \brief This file contains an abstraction interface for use with the cipher 5	 * primitives provided by the library. It provides a common interface to all of 6	 * the available cipher o…

### 14. `Bash`
- **asked:** command=grep -n "mbedtls_cipher_setup\|deprecated\|PSA" ~/ddb-targets/mbedtls/include/mbedtls/cipher.h | head -30
- **got:** 364:#if defined(MBEDTLS_USE_PSA_CRYPTO) && !defined(MBEDTLS_DEPRECATED_REMOVED) 367:     *  of the PSA Crypto API. 369:     *  mbedtls_cipher_setup(), and set if it was established through 370:     *  mbedtls_cipher_setu…

### 15. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/cipher.h
- **got:** 640	 641	#if defined(MBEDTLS_USE_PSA_CRYPTO) 642	#if !defined(MBEDTLS_DEPRECATED_REMOVED) 643	/** 644	 * \brief               This function initializes a cipher context for 645	 *                      PSA-based use with …

### 16. `Bash`
- **asked:** command=find ~/ddb-targets/mbedtls -name "README*" -type f | head -5
- **got:** ~/ddb-targets/mbedtls/tests/git-scripts/README.md ~/ddb-targets/mbedtls/docs/proposed/README ~/ddb-targets/mbedtls/README.md ~/ddb-targets/mbedtls/3rdparty/everest/README.md ~/ddb-targets/mbedtls/3rdparty/p256-m/README.m…

### 17. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/README.md
- **got:** 1	README for Mbed TLS 2	=================== 3	 4	Mbed TLS is a C library that implements cryptographic primitives (including the [PSA Cryptography API](#psa-cryptography-api)), X.509 certificate manipulation and the SSL/…

### 18. `Bash`
- **asked:** command=grep -A 20 "PSA Cryptography API" ~/ddb-targets/mbedtls/README.md
- **got:** Mbed TLS is a C library that implements cryptographic primitives (including the [PSA Cryptography API](#psa-cryptography-api)), X.509 certificate manipulation and the SSL/TLS and DTLS protocols. Its small code footprint …

**Reasoning.** Now let me look at specific examples of how these two interfaces expose the same operations:

### 19. `Bash`
- **asked:** command=grep -n "mbedtls_aes_crypt\|mbedtls_cipher" ~/ddb-targets/mbedtls/include/mbedtls/aes.h | head -20
- **got:** 247:int mbedtls_aes_crypt_ecb(mbedtls_aes_context *ctx, 295:int mbedtls_aes_crypt_cbc(mbedtls_aes_context *ctx, 340:int mbedtls_aes_crypt_xts(mbedtls_aes_xts_context *ctx, 389:int mbedtls_aes_crypt_cfb128(mbedtls_aes_con…

**Reasoning.** ## ANSWER

The mbedtls library exposes **two distinct public interfaces for the same cryptographic operations**:

### 1. Legacy mbedtls Interface (in `include/mbedtls/`)

This is the original, low-level cryptography API based on per-primitive modules:

- **AES operations**: `mbedtls_aes_init()`, `mbedtls_aes_setkey_enc()`, `mbedtls_aes_crypt_ecb()`, `mbedtls_aes_crypt_cbc()`, etc. (see `include/mbedtls/aes.h:107-247`)
- **Generic cipher abstraction**: `mbedtls_cipher_setup()`, `mbedtls_cipher_encrypt()`, `mbedtls_cipher_decrypt()` (see `include/mbedtls/cipher.h:638`)
- **Hash operations**: Fun

---

## Final answer as submitted

## ANSWER

The mbedtls library exposes **two distinct public interfaces for the same cryptographic operations**:

### 1. Legacy mbedtls Interface (in `include/mbedtls/`)

This is the original, low-level cryptography API based on per-primitive modules:

- **AES operations**: `mbedtls_aes_init()`, `mbedtls_aes_setkey_enc()`, `mbedtls_aes_crypt_ecb()`, `mbedtls_aes_crypt_cbc()`, etc. (see `include/mbedtls/aes.h:107-247`)
- **Generic cipher abstraction**: `mbedtls_cipher_setup()`, `mbedtls_cipher_encrypt()`, `mbedtls_cipher_decrypt()` (see `include/mbedtls/cipher.h:638`)
- **Hash operations**: Functions like `mbedtls_sha256()`, `mbedtls_md5()`, etc.

**Characteristics:**
- Stateful, context-based: requires explicit init/setup, key-setting, and free operations
- Direct buffer manipulation with raw key material
- Module-specific (one header per algorithm family: `aes.h`, `sha256.h`, etc.)

### 2. PSA Cryptography API (in `include/psa/`)

This is the standardized ARM Platform Security Architecture (PSA) Crypto interface:

- **Cipher operations**: `psa_cipher_encrypt()`, `psa_cipher_decrypt()`, `psa_cipher_encrypt_setup()`, `psa_cipher_update()` (see `include/psa/crypto.h:1633-1686`)
- **AEAD operations**: `psa_aead_encrypt()`, `psa_aead_decrypt()`
- **Key management**: `psa_import_key()`, `psa_generate_key()`, etc.

**Characteristics:**
- Key-based and policy-driven: keys are identified by opaque handles (`psa_key_id_t`), not raw material
- Requires `psa_crypto_init()` to be called before use
- Supports drivers for cryptographic accelerators and secure elements
- Unified interface across all algorithms

### How They Relate

**Origin and Direction:** PSA Crypto is the newer, standardized interface developed by ARM. The legacy mbedtls API predates PSA standardization. The library now supports both for backward compatibility, but PSA is the strategic direction.

**Bridge Function (Deprecated):** `mbedtls_cipher_setup_psa()` (in `include/mbedtls/cipher.h:641-673`) was a transitional bridge that attempted to wrap the legacy context interface with PSA operations. This function is **explicitly deprecated** with the message: *"Please use psa_aead_xxx() / psa_cipher_xxx() directly instead"* (line 649-650).

**Integration with TLS/X.509:** The library can route X.509 and TLS operations through either interface depending on the `MBEDTLS_USE_PSA_CRYPTO` compile flag (see `docs/use-psa-crypto.md:1-39`). TLS 1.3 **always uses PSA** regardless of this flag.

### Which Interface Should New Callers Use?

**Write against the PSA Cryptography API** (`psa_*` functions in `include/psa/crypto.h`). 

**Why:**

1. **Explicit deprecation guidance:** The bridge function deprecated the legacy wrapper with a direct recommendation to use `psa_cipher_xxx()` / `psa_aead_xxx()` directly (line 649).

2. **Driver support:** PSA is the only interface that can leverage cryptographic accelerators and secure elements via the PSA driver interface (see `README.md` PSA driver section).

3. **Standardization:** PSA Crypto is the ARM-standardized API; the legacy interface is library-specific.

4. **Strategic direction:** The README states *"Mbed TLS includes an implementation of the PSA Cryptography API"* and documents PSA as the primary interface; legacy functions exist for backward compatibility only.

5. **Policy-driven security:** PSA's key-based model with usage policies is superior to raw key material in the legacy API; keys never leave opaque handles.

6. **Future-proof:** New features (like TLS 1.3) default to PSA; legacy modules receive only maintenance.

---

## Gaps

No gaps found. The repository clearly documents both interfaces, their relationship, deprecation status, and migration path.
