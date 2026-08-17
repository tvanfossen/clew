# Q9 — src — haiku — run 1

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
