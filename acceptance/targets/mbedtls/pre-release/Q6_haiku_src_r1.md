# Q6 — src — haiku — run 1

Based on my source code analysis, here's where mbedtls handles certificate verification:

## Concept Overview

mbedtls implements X.509 certificate chain verification through a multi-stage process that validates:
1. Certificate chain completeness and trust anchoring
2. Digital signatures along the chain
3. Time validity of certificates
4. Security profile compliance (key strength, algorithm allowlists)
5. Hostname/domain name matching
6. Certificate revocation via CRL checks

## Entry Points

The public API is defined in `library/x509_crt.c` with four main entry functions:

- **`mbedtls_x509_crt_verify()`** at `library/x509_crt.c:3159` — Default profile verification
- **`mbedtls_x509_crt_verify_with_profile()`** at `library/x509_crt.c:3176` — Custom security profile
- **`mbedtls_x509_crt_verify_with_ca_cb()`** at `library/x509_crt.c:3195` — With trusted CA callback
- **`mbedtls_x509_crt_verify_restartable()`** at `library/x509_crt.c:3210` — ECDSA restartable version

All entry points delegate to the core implementation:

## Core Verification Pipeline

**Main orchestrator: `x509_crt_verify_restartable_ca_cb()`** at `library/x509_crt.c:3063-3153`

This function orchestrates the entire verification:
1. **Hostname verification** (line 3093): Calls `x509_crt_verify_name()` to check subject CN or SAN extensions
2. **Public key type/size validation** (lines 3097-3105): Validates key algorithm and strength against profile
3. **Chain verification** (line 3108): Calls `x509_crt_verify_chain()` to build and validate the certificate chain
4. **Flag aggregation** (line 3120): Merges verification flags and invokes user callback via `x509_crt_merge_flags_with_cb()`

**Certificate chain validation: `x509_crt_verify_chain()`** at `library/x509_crt.c:2511-2691`

Iterates through the certificate chain starting from the end-entity certificate:
- **Time validity checks** (lines 2572-2578): Verifies `valid_from` and `valid_to` against current time
- **Algorithm validation** (lines 2587-2593): Checks signature MD/PK algorithms against profile
- **Trusted EE exception** (line 2597): Allows locally-trusted end-entity certs
- **Parent search** (line 2628): Calls `x509_crt_find_parent()` to locate issuing CA
- **Intermediate limits** (lines 2662-2666): Enforces `MBEDTLS_X509_MAX_INTERMEDIATE_CA` path length
- **CRL verification** (line 2680): Calls `x509_crt_verifycrl()` to check revocation status

**Parent location and signature verification: `x509_crt_find_parent_in()`** at `library/x509_crt.c:2259-2358`

For each candidate parent certificate:
- **Parenting validation** (line 2297): Calls `x509_crt_check_parent()` — validates issuer name matches, CA bit set, key usage allows cert signing
- **Path length constraints** (lines 2302-2305): Enforces `max_pathlen` extension
- **Signature verification** (line 2311): Calls `x509_crt_check_signature()` to verify cryptographic signature
- **Time validity** (lines 2333-2341): Optional time check for parent CA with fallback mechanism

**Signature verification: `x509_crt_check_signature()`** at `library/x509_crt.c:2129-2177`

Performs cryptographic validation:
1. **Hash computation** (lines 2137-2156): Hashes the "to-be-signed" (TBS) data using the certificate's signature algorithm
2. **Algorithm compatibility check** (line 2160): Verifies parent's public key can perform the signature algorithm
3. **Signature verification** (lines 2174-2176): Calls `mbedtls_pk_verify_ext()` to verify the signature with parent's public key

**Hostname verification: `x509_crt_verify_name()`** at `library/x509_crt.c:2992-3014`

Validates the certificate's subject name matches the expected hostname:
- **SAN extension check** (lines 2999-3002): Prefers Subject Alternative Names via `x509_crt_check_san()`
- **CN fallback** (lines 3004-3009): Falls back to Common Name if SAN absent
- **Mismatch flagging** (line 3013): Sets `MBEDTLS_X509_BADCERT_CN_MISMATCH` if no match

**CRL verification: `x509_crt_verifycrl()`** at `library/x509_crt.c:2015-2125`

Checks if a certificate appears in a Certificate Revocation List:
1. **CRL issuer matching** (lines 2034-2038): Finds CRL signed by the CA in question
2. **CA key usage** (lines 2043-2047): Verifies CA has CRL signing permission via key usage extension
3. **CRL signature validation** (lines 2052-2093): Hashes CRL and verifies CA's signature
4. **Revocation status checking** (lines 2095-2127): Scans CRL entries for the certificate serial number

**Parent certificate validation: `x509_crt_check_parent()`** at `library/x509_crt.c:2185-2214`

Validates a parent is suitable:
- **Issuer name match** (line 2192): Certificate's issuer must equal parent's subject
- **CA bit check** (lines 2204-2206): Parent must have basicConstraints CA=true (with exception for v1/v2 locally-trusted roots)
- **Key usage** (line 2209): CA must have keyCertSign usage enabled

## Error Reporting

**Flag composition: `x509_crt_merge_flags_with_cb()`** at `library/x509_crt.c:3019-3061`

Aggregates verification failures across the chain and invokes user callback:
- Iterates backward through chain items
- Invokes user callback `f_vrfy()` for custom validation logic
- ORs all flags into output

## Configuration

**Security profiles** defined in `include/mbedtls/x509_crt.h:125-133`:
- `mbedtls_x509_crt_profile` controls allowed:
  - `allowed_mds`: Acceptable hash algorithms (SHA-256, SHA-384, etc.)
  - `allowed_pks`: Acceptable public key types (RSA, ECDSA, etc.)
  - `allowed_curves`: Acceptable elliptic curves for ECDSA
  - `rsa_min_bitlen`: Minimum RSA key size in bits

## Gaps

- I could not find the exact implementation of `x509_crt_check_san()` function that handles Subject Alternative Name matching in this read-through (it's likely in a companion source file or defined inline)
- The detailed revocation list entry parsing logic after line 2127 in `x509_crt_verifycrl()` was not fully examined
- The error flag definitions (`MBEDTLS_X509_BADCERT_*` constants) are defined elsewhere (likely in `include/mbedtls/x509.h`)
