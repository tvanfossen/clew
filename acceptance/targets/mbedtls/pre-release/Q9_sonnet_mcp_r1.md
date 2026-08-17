# Q9 — mcp — sonnet — run 1

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
