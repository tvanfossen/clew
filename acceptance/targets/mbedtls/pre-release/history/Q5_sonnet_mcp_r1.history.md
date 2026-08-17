# Q5 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"directories":[{"directory":"library","indexed_files":174,"symbols":4690,"external_files":0,"unresolved_files":0},{"directory":"include","indexed_files":97,"symbols":4057,"external_files":0,"unresolved_files":0},{"direc…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":6,"results":[{"file_path":"docs/architecture/alternative-implementations.md","heading":"alternative-implementations.md","snippet":"…This document is an >>overview<<. It is not exhaustive. …

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":174,"results":[{"path":"library/aes.c","symbol_count":80},{"path":"library/aesce.c","symbol_count":38},{"path":"library/aesce.h","symbol_count":4},{"path":"library/aesni.c","symbol_count":…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":74,"results":[{"path":"include/mbedtls/aes.h","symbol_count":31},{"path":"include/mbedtls/aria.h","symbol_count":20},{"path":"include/mbedtls/asn1.h","symbol_count":66},{"path":"include/mb…

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":80,"results":[{"path":"programs/README.md","symbol_count":0},{"path":"programs/aes/crypt_and_hash.c","symbol_count":5},{"path":"programs/cipher/cipher_aead_demo.c","symbol_count":21},{"pat…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
### 7. `Glob`
- **asked:** pattern=*.md, path=~/ddb-targets/mbedtls
- **got:** {"kind":"dossiers","count":5,"found":5,"subject":["mbedtls_ssl_handshake","psa_crypto_init","mbedtls_x509_crt_parse","mbedtls_pk_sign","mbedtls_ctr_drbg_seed"],"results":[{"subject":"mbedtls_ssl_handshake","subject_kind"…

- **got:** ~/ddb-targets/mbedtls/.github/ISSUE_TEMPLATE/bug_report.md ~/ddb-targets/mbedtls/.github/ISSUE_TEMPLATE/feature_request.md ~/ddb-targets/mbedtls/.github/pull_request_template.md ~/ddb-targets/mbedtls/3rdparty/everest/REA…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/README.md
- **got:** 1	README for Mbed TLS 2	=================== 3	 4	Mbed TLS is a C library that implements cryptographic primitives (including the [PSA Cryptography API](#psa-cryptography-api)), X.509 certificate manipulation and the SSL/…

**Reasoning.** ## What Mbed TLS does

Mbed TLS is a C library implementing cryptographic primitives, the PSA Cryptography API, X.509 certificate handling, and SSL/TLS + DTLS protocols, aimed at embedded/small-footprint use (README.md:1-4).

## Where to start reading

1. `README.md:1-40` — top-level orientation: three build systems (Make/CMake/MSVC), config lives in `include/mbedtls/mbedtls_config.h`.
2. `include/mbedtls/ssl.h` (606 symbols — the largest header in the index) and `library/ssl_tls.c` (314 symbols, the largest library source) — the TLS/DTLS state machine. Entry point `mbedtls_ssl_handshake()` (`

---

## Final answer as submitted

## What Mbed TLS does

Mbed TLS is a C library implementing cryptographic primitives, the PSA Cryptography API, X.509 certificate handling, and SSL/TLS + DTLS protocols, aimed at embedded/small-footprint use (README.md:1-4).

## Where to start reading

1. `README.md:1-40` — top-level orientation: three build systems (Make/CMake/MSVC), config lives in `include/mbedtls/mbedtls_config.h`.
2. `include/mbedtls/ssl.h` (606 symbols — the largest header in the index) and `library/ssl_tls.c` (314 symbols, the largest library source) — the TLS/DTLS state machine. Entry point `mbedtls_ssl_handshake()` (`library/ssl_tls.c:4677-4710`), which drives the state machine via `mbedtls_ssl_handshake_step` (dossier callee).
3. `include/psa/crypto.h:8609` / `library/psa_crypto.c` — `psa_crypto_init()`, the mandatory init call for the newer PSA crypto surface that the legacy API increasingly wraps.
4. `library/x509_crt.c:1399-1507` (`mbedtls_x509_crt_parse`) — certificate parsing, called from both `main()` (a test/program driver) and the fuzzer harness (`LLVMFuzzerTestOneInput`).

## Major parts (by directory, from the index's file rollup)

| Directory | Indexed files | Symbols | Role |
|---|---|---|---|
| `library/` | 174 | 4,690 | The implementation: crypto primitives (`aes.c`, `sha256.c`, `bignum.c`, `ecp.c`, `rsa.c`...), PSA crypto (`psa_crypto*.c`), X.509 (`x509*.c`), and SSL/TLS (`ssl_tls*.c`, `ssl_tls12_*`, `ssl_tls13_*`, `ssl_msg.c`) |
| `include/mbedtls/`, `include/psa/` | 97 | 4,057 | Public API headers — the surface a consumer links against |
| `programs/` | 80 | 965 | Example/utility binaries: `ssl/` (client/server demos, incl. `ssl_pthread_server.c` for a threaded server), `x509/`, `pkey/`, `psa/`, `fuzz/` (OSS-Fuzz harnesses), `test/` (benchmark, selftest, udp_proxy) |
| `tests/` | 44 | 859 | Test framework + generated test code |
| `3rdparty/` | 32 | 454 | Declared vendored code (`everest`, `p256-m`) — committed but not authored here |
| `configs/`, `scripts/`, `docs/` | 13/9/30 | 143/141/12 | Alternate build configs, dev tooling, architecture docs (`docs/architecture/tls13-support.md`, `docs/use-psa-crypto.md`, etc.) |

Structurally, `library/` splits into three layers, confirmed via `dossier` call graphs:
- **Crypto primitives** (`aes.c`, `bignum*.c`, `sha*.c`, `ecp*.c`, `rsa.c`, `ctr_drbg.c`) — e.g. `mbedtls_ctr_drbg_seed()` (`library/ctr_drbg.c:535-588`) seeds the DRBG from an entropy callback.
- **PSA crypto** (`psa_crypto*.c`, 155 symbols in `psa_crypto.c` alone) — the newer unified crypto API; `psa_crypto_init()` is called from `main()`, from TLS 1.3 crypto init (`mbedtls_ssl_tls13_crypto_init`), and from the fuzzer entry point.
- **PKI/TLS** (`pk*.c`, `x509*.c`, `ssl_*.c`) — `mbedtls_pk_sign()` (`library/pk.c:1382-1390`) delegates to `mbedtls_pk_sign_restartable`, and is called from certificate-writing code (`mbedtls_x509write_crt_der`) and from TLS server key-exchange (`ssl_prepare_server_key_exchange`).

The index also surfaced one concrete thread: `handle_ssl_connection`, spawned via `pthread_create` in `programs/ssl/ssl_pthread_server.c:277`, whose reachable set includes `mbedtls_ssl_handshake`, `psa_crypto_init`, and `mbedtls_pk_sign` — i.e. the threaded demo server exercises the full crypto→PKI→TLS stack in one worker thread.

## Coverage of this answer

- The index holds **527 files** total; I queried the four largest source trees (`library`, `include`, `programs`, plus the top-level rollup) and read `README.md` directly. I did **not** examine `tests/` (44 files/859 symbols), `3rdparty/` (32 files, vendored), `configs/`, `scripts/`, or the 30 architecture docs under `docs/` beyond their titles from a prose search.
- Within `library/` and `include/`, I dossier'd 5 representative entry points (`mbedtls_ssl_handshake`, `psa_crypto_init`, `mbedtls_x509_crt_parse`, `mbedtls_pk_sign`, `mbedtls_ctr_drbg_seed`) out of ~271 files / ~8,700 symbols in those two trees combined — enough to confirm the layering and a real call path between the crypto/PSA/PKI/TLS layers, not to characterize every module (e.g. ECC curve internals, TLS 1.3 key schedule, ASN.1 writers were named but not read).

## Gaps

- Did not read `tests/`, `3rdparty/`, `configs/`, or `scripts/` beyond directory-level counts.
- Did not open the 30 architecture docs under `docs/architecture/` beyond the prose-search snippets shown above (titles/one-line excerpts only) — these likely contain more authoritative design rationale (e.g. `tls13-support.md`, `psa-crypto-implementation-structure.md`) than I've relayed.
- Did not trace the requirements/coverage layer (`covering_tests`, `requirements` came back empty on all 5 dossiers) — this repo doesn't appear to carry `@req`-tagged requirements, so I can't say whether that's a real absence or an untagged convention.
- Everything above came from the index (`search`/`dossier`) plus one direct `Read` of `README.md`; no `Grep`/source sweep was needed.
