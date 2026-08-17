# Q9 — mcp — haiku — run 1

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
