# Q6 — src — sonnet — run 1

I have enough to give a complete, well-grounded answer.

## Certificate verification in mbedTLS

**Concept location:** mbedTLS handles X.509 certificate-chain verification in two layers: a protocol-agnostic X.509 library (`library/x509_crt.c`) that does the actual cryptographic/chain-of-trust checks, and the TLS handshake code (`library/ssl_tls.c`, `library/ssl_tls13_generic.c`) that invokes it at the right point during a handshake and applies TLS-specific policy (authmode, hostname).

### 1. TLS handshake entry point
- `mbedtls_ssl_parse_certificate()` (`library/ssl_tls.c:8052`) reads the peer's `Certificate` handshake message, builds an `mbedtls_x509_crt` chain (`library/ssl_tls.c:8107-8120`), then calls verification at `library/ssl_tls.c:8136`.
- Used both by TLS 1.2 (`ssl_tls.c:8136`) and TLS 1.3 (`library/ssl_tls13_generic.c:729`, calling the same function).
- `mbedtls_ssl_verify_certificate()` (`library/ssl_tls.c:9915`) is the shared entry:
  - Short-circuits with success if `authmode == MBEDTLS_SSL_VERIFY_NONE` (`ssl_tls.c:9921-9924`).
  - Resolves the hostname to check via `get_hostname_for_verification()` (`ssl_tls.c:9894-9913`), refusing (in strict builds) client verification with no hostname set (`ssl_tls.c:9899-9903`).
  - Selects either the CA-callback verify path `mbedtls_x509_crt_verify_with_ca_cb()` (`ssl_tls.c:9955`) or the static CA-chain path `mbedtls_x509_crt_verify_restartable()` (`ssl_tls.c:9983`), passing `ssl->conf->cert_profile`, the hostname, and an app-supplied `f_vrfy` callback.
  - Applies secondary TLS-1.2-only checks afterward, e.g. EC curve acceptability (`ssl_tls.c:10013-10019`), and (elsewhere at `ssl_tls.c:9869-9889`) key-usage / extended-key-usage checks (`MBEDTLS_X509_KU_DIGITAL_SIGNATURE`, `serverAuth`/`clientAuth` OIDs).

### 2. X.509 chain verification core (`library/x509_crt.c`)
- Public entry points, all funneling into one restartable worker:
  - `mbedtls_x509_crt_verify()` (`x509_crt.c:3159`)
  - `mbedtls_x509_crt_verify_with_profile()` (`x509_crt.c:3176`)
  - `mbedtls_x509_crt_verify_with_ca_cb()` (`x509_crt.c:3195`, guarded by `MBEDTLS_X509_TRUSTED_CERTIFICATE_CALLBACK`)
  - `mbedtls_x509_crt_verify_restartable()` (`x509_crt.c:3210`)
  - All call `x509_crt_verify_restartable_ca_cb()` (`x509_crt.c:3063`), which:
    - Checks CN/SAN via `x509_crt_verify_name()` (`x509_crt.c:2992`, called at `x509_crt.c:3093`) — SAN checked first if present (`x509_crt.c:2999-3001`), else CN attribute (`x509_crt.c:3004-3009`); mismatch sets `MBEDTLS_X509_BADCERT_CN_MISMATCH` (`x509_crt.c:3013`).
    - Checks the end-entity key's algorithm/size against the profile (`x509_crt.c:3097-3105`).
    - Builds/verifies the chain via `x509_crt_verify_chain()` (`x509_crt.c:3108`, defined at `x509_crt.c:2511`).
    - Merges per-certificate flags and invokes the optional app callback via `x509_crt_merge_flags_with_cb()` (`x509_crt.c:3019`, called at `x509_crt.c:3120`).
    - Fails closed: a non-zero `f_vrfy` return is treated as fatal even under "optional" authmode (`x509_crt.c:3139-3141`); any nonzero merged flags produce `MBEDTLS_ERR_X509_CERT_VERIFY_FAILED` (`x509_crt.c:3148-3150`).

- `x509_crt_verify_chain()` (`x509_crt.c:2511-2691`) is the actual chain walk:
  - Per-certificate time validity: expired (`x509_crt.c:2572-2574`) / not-yet-valid (`x509_crt.c:2576-2578`) checks against `mbedtls_x509_time_gmtime(now)` (`x509_crt.c:2536`).
  - Stops successfully once it reaches a trusted root (`x509_crt.c:2582-2584`) or a locally-trusted EE cert (`x509_crt.c:2596-2599`, via `x509_crt_check_ee_locally_trusted`).
  - Signature/MD/PK algorithm checks against the profile (`x509_crt.c:2587-2593`).
  - Finds the issuing parent — from a CA callback (`x509_crt.c:2607-2625`) or the static trusted list — via `x509_crt_find_parent()` (declared `x509_crt.c:2382`, which internally uses `x509_crt_find_parent_in()` at `x509_crt.c:2259` and `x509_crt_check_signature()` at `x509_crt.c:2129` to cryptographically verify the signature, and `x509_crt_check_parent()` at `x509_crt.c:2185` to check issuer/subject name and key-identifier matching).
  - No parent found → `MBEDTLS_X509_BADCERT_NOT_TRUSTED` (`x509_crt.c:2648`); bad signature → same flag (`x509_crt.c:2669-2671`).
  - Enforces `MBEDTLS_X509_MAX_INTERMEDIATE_CA` path length (`x509_crt.c:2662-2666`), tracking self-issued certs specially (`x509_crt.c:2652-2658`, referencing the "[SIRO]" key-rollover case).
  - CRL revocation check per parent via `x509_crt_verifycrl()` (declared `x509_crt.c:2015`, invoked `x509_crt.c:2680`) when `MBEDTLS_X509_CRL_PARSE_C` is enabled.
  - Loops up the chain (`child = parent`, `x509_crt.c:2686`) until a trust anchor or failure.

### 3. Restartable / ECDSA-async support
Verification supports cooperative restart for slow ECDSA ops (`MBEDTLS_ECDSA_C && MBEDTLS_ECP_RESTARTABLE`): state is saved/resumed via `rs_ctx` (`x509_crt.c:2541-2555`, `2633-2644`), letting `mbedtls_x509_crt_verify_restartable()` be re-entered without redoing prior work — surfaced to TLS via `MBEDTLS_ERR_ECP_IN_PROGRESS` → `MBEDTLS_ERR_SSL_CRYPTO_IN_PROGRESS` (`ssl_tls.c:9997-9999`).

### Header-level API surface (for reference)
`include/mbedtls/x509_crt.h`: declarations of `mbedtls_x509_crt_verify()` (`x509_crt.h:670`), `_with_profile()` (`x509_crt.h:711`), `_restartable()` (`x509_crt.h:745`), `_with_ca_cb()` (`x509_crt.h:811`), plus the `mbedtls_x509_crt_verify_chain` struct (`x509_crt.h:264`, `274`) used to carry per-certificate flags through the chain walk.

## Gaps

- I did not trace `x509_crt_check_signature()` (`library/x509_crt.c:2129`) or `x509_crt_check_parent()` (`library/x509_crt.c:2185`) body-by-body — cited their existence/role from their call sites and names but did not read their full implementations line-by-line.
- I did not examine `x509_crt_verifycrl()`'s internals (`library/x509_crt.c:2015`) beyond its call site — CRL-specific revocation-check logic is unread.
- I did not check `programs/` or `tests/` for example/test call sites — scope was the library's own handling of the concept, which the TLS + X.509 layers above fully cover.
- Certificate *parsing* (ASN.1/ANSI DER decode in `x509_crt.c` earlier sections) was not investigated; the question was about verification, not parsing.
