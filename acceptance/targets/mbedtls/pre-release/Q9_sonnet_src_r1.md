# Q9 — src — sonnet — run 1

That's enough evidence. Here's the answer.

## Answer

Mbed TLS ships **two parallel public APIs for the same cryptographic operations**, and the repository's own docs are explicit that this is a deliberate, time-boxed transition rather than two co-equal designs:

### 1. The legacy `mbedtls_xxx` API
Per-mechanism headers/modules, each with its own function family and its own context struct — e.g. `include/mbedtls/gcm.h` (`mbedtls_gcm_*`), `include/mbedtls/aes.h` (`mbedtls_aes_*`), `include/mbedtls/rsa.h`, `include/mbedtls/ecdsa.h`, `include/mbedtls/md.h`, `include/mbedtls/cipher.h`, etc. `docs/psa-transition.md:106-174` gives the full header→prefix table. Key material lives directly in application memory inside these contexts (`docs/psa-transition.md:35`), and each operation type has its own bespoke calling convention (`docs/psa-transition.md:34,36-37`).

### 2. The PSA Crypto API
A single unified header, `#include <psa/crypto.h>` (`docs/psa-transition.md:61`), with algorithm-agile functions (`psa_cipher_*`, `psa_aead_*`, `psa_mac_*`, `psa_sign_*`, etc., declared in `include/psa/crypto.h`) that dispatch on `psa_algorithm_t`/`psa_key_type_t` values rather than having one function family per cipher (`docs/psa-transition.md:291-293`). Keys are referenced indirectly via opaque `psa_key_id_t` handles rather than being embedded in the operation context (`docs/psa-transition.md:88-102`), which is what allows keys to live in a secure element/HSM. All PSA functions require `psa_crypto_init()` to have been called first (`include/psa/crypto.h:87,106`, and `docs/psa-transition.md:68`).

### How they relate
This isn't two independent designs — it's a documented, in-progress migration:
- `docs/psa-transition.md:1-9`: "Mbed TLS is gradually moving from legacy `mbedtls_xxx` APIs to newer `psa_xxx` APIs for cryptography."
- The migration timeline (`docs/psa-transition.md:39-45`) states legacy crypto APIs are slated for removal: "TF-PSA-Crypto 1.0.0 and Mbed TLS 4.0.0 (Oct 2025): Removal of most legacy crypto APIs. X.509 and TLS require the PSA API," and "Mbed TLS 5.0.0 (??): Removal of the remaining non-PSA crypto APIs."
- There's a bridging mechanism, `MBEDTLS_USE_PSA_CRYPTO` (documented separately in `docs/use-psa-crypto.md:1-9`), which makes the higher-level X.509/TLS/PK modules route their internal crypto calls through PSA instead of the legacy layer — a config flag for the *plumbing*, not a third public crypto API.
- Some legacy-facing conveniences have already been explicitly deprecated in favor of the PSA equivalent, e.g. `mbedtls_cipher_setup_psa()`: "This function only worked for a small number of ciphers. It is now deprecated and it is recommended to use `psa_cipher_xxx()` or `psa_aead_xxx()` functions directly instead. **Warning:** This function will be removed in a future version" (`docs/use-psa-crypto.md:119-128`).
- Not everything has a PSA equivalent yet — `nist_kw.h`, `bignum.h`/`mbedtls_mpi_`, and PK/ASN.1/base64 "format support" interfaces stay legacy-only per the table at `docs/psa-transition.md:106-174` (e.g. row 144: `nist_kw.h` → "Migration path not yet defined"; row 113: `bignum.h` → "None (no low-level arithmetic)").

### Which one to write against
**A new caller should write against the PSA Crypto API (`psa/crypto.h`).** The repo's own migration guide gives explicit rationale, all under `docs/psa-transition.md:32-37`:
- Opaque, driver-friendly design vs. legacy's transparent-struct design that blocks hardware acceleration.
- Native support for keys that never enter application memory (secure element/HSM), which the legacy API cannot do at all.
- Consistent, checked-buffer-size conventions across all PSA functions, vs. inconsistent legacy conventions.
- An internal, no-argument-passing global RNG, avoiding a historical class of legacy bugs where functions were later bolted onto an RNG argument as a security fix.

And decisively: the legacy APIs are the ones being removed on a stated timeline (Mbed TLS 4.0.0/5.0.0, `docs/psa-transition.md:39-45`), so writing new code against `mbedtls_xxx` is writing against a deprecating surface, not a stable one. The one carve-out: for functionality PSA doesn't cover yet (documented per-header in the migration table, e.g. `nist_kw.h`, ASN.1/PEM/base64 parsing, `pk.h` for key-pair parsing/formatting), the doc itself says to keep including those specific legacy headers (`docs/psa-transition.md:64`).

## Gaps

- I read `docs/psa-transition.md` only through line 384 of 1349 (it was paginated/truncated in my tool output); the per-mechanism migration sections further down (symmetric encryption details, hashes/MAC, asymmetric crypto specifics) weren't fully reviewed, though the summary table and top-level guidance I cited were captured in the portion I read.
- I did not exhaustively check every header in `include/mbedtls/` and `include/psa/` for exact overlap (e.g. confirming every legacy module has a PSA counterpart) — I relied on the migration table at `docs/psa-transition.md:106-174`, which is the repository's own authoritative mapping, rather than re-deriving it from source headers.
