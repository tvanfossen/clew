# Q6 — mcp — haiku — run 1

Based on my search through the mbedtls index, I can provide a comprehensive answer about certificate verification in this codebase.

## Certificate Verification Architecture

mbedtls handles certificate verification through a layered architecture with **three levels**: public API, SSL integration, and core verification logic.

### Public Entry Points

**Primary public APIs:**
- `mbedtls_x509_crt_verify()` — verifies a certificate chain against trusted CAs `include/mbedtls/x509_crt.h:3159`
- `mbedtls_x509_crt_verify_with_profile()` — verifies with a security profile `include/mbedtls/x509_crt.h:3159` (depth 1 call to restartable version)
- `mbedtls_x509_crt_verify_restartable()` — restartable version for interruptible verification `include/mbedtls/x509_crt.h:3159` (depth 1 wrapper)

**SSL/TLS integration:**
- `mbedtls_ssl_verify_certificate()` — called during SSL handshake `library/ssl_tls.c:9915`, which invokes either `mbedtls_x509_crt_verify_with_ca_cb()` or `mbedtls_x509_crt_verify_restartable()` based on CA callback availability

### Core Verification Pipeline

The main verification flow starts with `x509_crt_verify_restartable_ca_cb()` `library/x509_crt.c:3063`, which coordinates four sequential checks:

1. **Name Verification** — `x509_crt_verify_name()` `library/x509_crt.c:2992`
   - Checks subjectAltNames extension first
   - Falls back to CN component in Subject name
   - Sets `BADCERT_CN_MISMATCH` flag on failure

2. **Public Key and Algorithm Checks** — performed in the main function
   - `mbedtls_x509_profile_check_pk_alg()` — validates PK algorithm against security profile
   - `x509_profile_check_key()` — validates key size and type

3. **Chain Verification** — `x509_crt_verify_chain()` `library/x509_crt.c:2511`
   - Builds the certificate chain from end-entity to root
   - For each certificate in chain:
     - **Time validation** `library/x509_crt.c:2542` — checks `valid_from` and `valid_to` against current time via `mbedtls_x509_time_cmp()`
     - **Signature algorithm checks** — MD and PK algorithms via `mbedtls_x509_profile_check_md_alg()` and `mbedtls_x509_profile_check_pk_alg()`
     - **Parent finding** — `x509_crt_find_parent()` `library/x509_crt.c:2382` searches for signing certificate
     - **CRL verification** — `x509_crt_verifycrl()` `library/x509_crt.c:2015` if CRL list provided

4. **Signature Cryptographic Verification** — `x509_crt_find_parent_in()` `library/x509_crt.c:2259`
   - `x509_crt_check_parent()` `library/x509_crt.c:2185` validates:
     - Issuer name matches parent's subject
     - Parent has CA bit set (exception for v1/v2 locally-trusted certs)
     - Parent has KEY_CERT_SIGN key usage
     - Path length constraints respected
   - `x509_crt_check_signature()` `library/x509_crt.c:2129` performs actual cryptographic verification:
     - Hashes certificate TBS (To-Be-Signed) with signature algorithm's hash function
     - Uses `mbedtls_pk_verify_ext()` to verify signature against parent's public key
     - Supports restartable ECDSA via `mbedtls_pk_verify_restartable()`

### Revocation Checking

**CRL-based revocation** — `x509_crt_verifycrl()` `library/x509_crt.c:2015`:
- Validates CRL signature against the issuing CA
- Checks CRL time validity (`this_update`, `next_update`)
- Calls `mbedtls_x509_crt_is_revoked()` `library/x509_crt.c:1995` to check if certificate serial number is in the CRL

### Callback Integration

The verification process accepts optional callbacks:
- `f_vrfy` — user-supplied verification callback per-certificate, allowing applications to override decisions `include/mbedtls/x509_crt.h:3159` (documented in detail there)
- `f_ca_cb` — trusted certificate callback for dynamic CA provision `library/ssl_tls.c:9928`

### Security Profile Enforcement

Verification respects configured security profiles via `mbedtls_x509_crt_profile` parameter, which gates acceptable algorithms and key sizes at multiple check points throughout the chain.

## Gaps

- I could not locate the implementation of the CN matching logic inside `x509_crt_check_cn()` or `x509_crt_check_san()` by name alone (the index found them as callees but their definitions weren't reached in dossier output). These perform the actual hostname/DNS name matching.
- Algorithm profile validation code (`mbedtls_x509_profile_check_md_alg`, `mbedtls_x509_profile_check_pk_alg`) is defined in the index but full implementation not fetched.
