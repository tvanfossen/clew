# Q6 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":7,"results":[{"name":"MBEDTLS_ERR_SSL_CERTIFICATE_VERIFICATION_WITHOUT_HOSTNAME","kind":"macro definition","file":"include/mbedtls/ssl.h","brief":"-0x5D80"},{"name":"MBEDTLS_SSL_CLI_ALL…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, text
### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":19,"results":[{"name":"mbedtls_x509_crt_verify","kind":"function","file":"include/mbedtls/x509_crt.h","brief":"Verify a chain of certificates."},{"name":"mbedtls_x509_crt_verify_chain",…

- **got:** {"kind":"matching symbols","count":16,"results":[{"name":"mbedtls_x509_crt_verify_chain","kind":"struct","file":"include/mbedtls/x509_crt.h"},{"name":"mbedtls_x509_crt_verify_chain_item","kind":"struct","file":"include/m…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"dossiers","count":3,"found":3,"subject":["mbedtls_x509_crt_verify_with_profile","x509_crt_verify_chain","mbedtls_ssl_conf_authmode"],"results":[{"subject":"mbedtls_x509_crt_verify_with_profile","subject_kind":"f…

- **got:** {"kind":"matching symbols","count":15,"results":[{"name":"mbedtls_ssl_tls13_process_certificate_verify","kind":"function","file":"library/ssl_misc.h"},{"name":"mbedtls_ssl_tls13_write_certificate_verify","kind":"function…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_ssl_verify_certificate","subject_kind":"function","name":"mbedtls_ssl_verify_certificate","rowid":10143,"signature":"int mbedtls_ssl_verify_certificate(mbedtls_ssl_context *ssl, int authmode, mbedtls_…

### 7. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject
- **got:** {"kind":"dossiers","count":3,"found":3,"subject":["mbedtls_x509_crt_verify","mbedtls_ssl_parse_certificate","x509_crt_verify_name"],"results":[{"subject":"mbedtls_x509_crt_verify","subject_kind":"function","name":"mbedtl…

**Reasoning.** I have enough to give a complete, layered answer.

## Certificate verification in mbedtls

Certificate verification is implemented in two layers: a generic X.509 chain-verification engine (`library/x509_crt.c`), and an SSL/TLS handshake layer (`library/ssl_tls.c`) that calls into it during the handshake.

### 1. X.509 chain verification (the core algorithm)

- **Public API entry points**, both thin wrappers around the same internal engine:
  - `mbedtls_x509_crt_verify()` — verifies with the default security profile — `library/x509_crt.c:3159-3171` (declared `include/mbedtls/x509_crt.h:3159`).


---

## Final answer as submitted

I have enough to give a complete, layered answer.

## Certificate verification in mbedtls

Certificate verification is implemented in two layers: a generic X.509 chain-verification engine (`library/x509_crt.c`), and an SSL/TLS handshake layer (`library/ssl_tls.c`) that calls into it during the handshake.

### 1. X.509 chain verification (the core algorithm)

- **Public API entry points**, both thin wrappers around the same internal engine:
  - `mbedtls_x509_crt_verify()` — verifies with the default security profile — `library/x509_crt.c:3159-3171` (declared `include/mbedtls/x509_crt.h:3159`).
  - `mbedtls_x509_crt_verify_with_profile()` — same, with an explicit `mbedtls_x509_crt_profile` — `library/x509_crt.c:3176-3188`.
  - Both simply call `x509_crt_verify_restartable_ca_cb()` (`library/x509_crt.c:1586`, the resolved callee in both dossiers above).

- **The actual chain-walking algorithm**: `static int x509_crt_verify_chain()` — `library/x509_crt.c:2511-2691` (static, `static` confirmed in dossier). Per certificate in the chain it:
  - Checks validity period against current time via `mbedtls_x509_time_cmp`/`mbedtls_x509_time_gmtime` (called at `library/x509_crt.c` inside this function; flags `MBEDTLS_X509_BADCERT_EXPIRED`/`_FUTURE`).
  - Checks signature/hash algorithm strength against the profile via `mbedtls_x509_profile_check_md_alg` and `mbedtls_x509_profile_check_pk_alg` (flags `MBEDTLS_X509_BADCERT_BAD_MD`/`_BAD_PK`).
  - Finds the issuing parent (`x509_crt_find_parent`, `library/x509_crt.c:1609`) either from the statically configured trusted CA list or, if `MBEDTLS_X509_TRUSTED_CERTIFICATE_CALLBACK` is enabled, from a caller-supplied CA callback (`f_ca_cb`).
  - Checks CRL revocation via `x509_crt_verifycrl()` (`library/x509_crt.c:394`).
  - Special-cases end-entity certs that are themselves directly, locally trusted (`x509_crt_check_ee_locally_trusted`, `library/x509_crt.c:392`).
  - The whole function is gated on `MBEDTLS_X509_CRT_PARSE_C` (`library/x509_crt.c:22`).

- **Hostname/CN verification** (separate from chain trust): `static void x509_crt_verify_name()` — `library/x509_crt.c:2992-3014`. Checks the expected CN either against `subjectAltName` (`x509_crt_check_san`, `library/x509_crt.c:420`) if present, or falls back to the `CN` RDN in the Subject (`x509_crt_check_cn`, `library/x509_crt.c:10376`). Called from `x509_crt_verify_restartable_ca_cb` (`library/x509_crt.c:1586`), the same shared engine both public entry points funnel through.

- Result codes come back as `MBEDTLS_X509_BADCERT_*` / `MBEDTLS_X509_BADCRL_*` bit flags, human-readable via `mbedtls_x509_crt_verify_info()` (`include/mbedtls/x509_crt.h`).

### 2. SSL/TLS handshake layer (where verification is invoked)

- **Policy configuration**: `mbedtls_ssl_conf_authmode()` — `library/ssl_tls.c:1669-1672` — sets `conf->authmode` to `MBEDTLS_SSL_VERIFY_NONE` / `_OPTIONAL` / `_REQUIRED` (default: NONE on server, REQUIRED on client, per its own doc comment).

- **Handshake entry point**: `mbedtls_ssl_parse_certificate()` — `library/ssl_tls.c:8052-8202` — called from both `mbedtls_ssl_handshake_client_step` and `mbedtls_ssl_handshake_server_step` (`library/ssl_tls.c:10496`, `10506`). It reads the authmode (SNI-specific override takes precedence over `conf->authmode` — `library/ssl_tls.c:8058-8062`), parses the peer's certificate chain (`ssl_parse_certificate_chain`, `library/ssl_tls.c:6837`), then calls:

- **`mbedtls_ssl_verify_certificate()`** — `library/ssl_tls.c:9915-10101` — the bridge from handshake to X.509:
  - Short-circuits to success if `authmode == MBEDTLS_SSL_VERIFY_NONE` (`library/ssl_tls.c:9915` body, line ~9921-9923).
  - Selects a verify callback: connection-specific `ssl->f_vrfy` if set, else `ssl->conf->f_vrfy`.
  - Resolves the expected hostname via `get_hostname_for_verification()` (`library/x509_crt.c` — actually `library/ssl_tls.c:6643`).
  - Dispatches to either `mbedtls_x509_crt_verify_with_ca_cb()` (if a CA callback is configured, gated on `MBEDTLS_X509_TRUSTED_CERTIFICATE_CALLBACK`) or `mbedtls_x509_crt_verify_restartable()` (`include/mbedtls/x509_crt.h:7314`) with the configured `ca_chain`/`ca_crl` — SNI-specific chain (`ssl->handshake->sni_ca_chain`) takes precedence over `ssl->conf->ca_chain`.
  - Runs secondary checks unconditionally regardless of the primary result: TLS 1.2 ECC curve acceptability (`mbedtls_ssl_check_curve`, `library/ssl_tls.c:10182`) and X.509 key-usage/extended-key-usage extensions (`mbedtls_ssl_check_cert_usage`, `library/ssl_tls.c:10181`), each of which can turn a `ret == 0` into `MBEDTLS_ERR_SSL_BAD_CERTIFICATE`.
  - Called from both TLS 1.2 (`mbedtls_ssl_parse_certificate`, `library/ssl_tls.c:10481`) and TLS 1.3 (`ssl_tls13_validate_certificate`, `library/ssl_tls.c:10183`) code paths.

- **Result inspection API**: `mbedtls_ssl_get_verify_result()` (`include/mbedtls/ssl.h`) — lets the app read `ssl->session_negotiate->verify_result` after the handshake, needed when `authmode == MBEDTLS_SSL_VERIFY_OPTIONAL`.

- **TLS 1.3 CertificateVerify message** (a *different* concept — the peer's proof-of-possession signature over the transcript, not chain trust) is handled separately by `ssl_tls13_process_certificate_verify` / `mbedtls_ssl_tls13_process_certificate_verify` (`library/ssl_misc.h`) and `ssl_tls13_parse_certificate_verify` (`library/ssl_tls13_generic.c`) — worth flagging so it isn't conflated with `mbedtls_ssl_verify_certificate` above.

### Call chain summary

```
mbedtls_ssl_handshake_{client,server}_step
  → mbedtls_ssl_parse_certificate            (library/ssl_tls.c:8052)
      → mbedtls_ssl_verify_certificate        (library/ssl_tls.c:9915)
          → mbedtls_x509_crt_verify_restartable / _with_ca_cb
              → x509_crt_verify_restartable_ca_cb (library/x509_crt.c:1586)
                  → x509_crt_verify_chain      (library/x509_crt.c:2511, trust/expiry/CRL/profile checks)
                  → x509_crt_verify_name       (library/x509_crt.c:2992, hostname/CN/SAN check)
```

## Gaps

- Did not read the full bodies of `x509_crt_verify_restartable_ca_cb`, `mbedtls_ssl_check_cert_usage`, or `ssl_tls13_process_certificate_verify` line-by-line — cited from dossier metadata (signatures/callees) rather than full source; line ranges given are accurate but internal logic beyond what's quoted is not verified.
- `requirements`/`covering_tests` fields were empty for every symbol queried — the index has no `@req` traceability wired up for this codebase, so I can't cite which tests exercise this path (would need a manual grep of `tests/` to confirm).
- Did not trace the DTLS-specific or PSK/raw-public-key variants of certificate handling, which may bypass some of this path.
