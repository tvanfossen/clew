# Q11 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":0,"results":[],"subject":"config","note":"No indexed file matches 'config'. This corpus holds INDEXED SOURCE FILES only, so a build script, a Doxyfile, a data file or anything else the ind…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":25,"results":[{"file_path":"include/mbedtls/mbedtls_config.h","heading":"include/mbedtls/mbedtls_config.h — file-level documentation","snippet":"include/mbedtls/mbedtls_config.h \\file mbe…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":1,"results":[{"path":"scripts/config.py","symbol_count":26}],"subject":"scripts/config.py","inventory":{"directories":[{"directory":"library","indexed_files":174,"symbols":4690,"external_f…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossier","subject":"check_config.h","found":false,"note":"No dossier for 'check_config.h' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before concluding …

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":25,"results":[{"file_path":"include/mbedtls/build_info.h","heading":"include/mbedtls/build_info.h — file-level documentation","snippet":"…this file if you need to depend on the configurati…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":3,"found":0,"subject":["include/mbedtls/check_config.h","include/mbedtls/mbedtls_config.h","README.md"],"results":[{"name":"include/mbedtls/check_config.h","found":false,"note":"Not indexed in …

### 7. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":2,"found":0,"subject":["check_config.h","mbedtls_config.h"],"results":[{"name":"check_config.h","found":false,"note":"Not indexed in this repository. A definitive negative from the database, no…

### 8. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 1	/** 2	 * \file mbedtls_config.h 3	 * 4	 * \brief Configuration options (set of defines) 5	 * 6	 *  This set of compile-time options may be used to enable 7	 *  or disable features selectively, and reduce the global 8	 …

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/build_info.h
- **got:** 1	/** 2	 * \file mbedtls/build_info.h 3	 * 4	 * \brief Build-time configuration info 5	 * 6	 *  Include this file if you need to depend on the 7	 *  configuration options defined in mbedtls_config.h or MBEDTLS_CONFIG_FIL…

### 10. `Bash`
- **asked:** command=grep -n "MBEDTLS_SSL_PROTO_TLS1_3" ~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h | head -20
- **got:** 1773: * \note This option is required if MBEDTLS_SSL_PROTO_TLS1_3 is set. 1832: * Requires: MBEDTLS_SSL_PROTO_TLS1_3 1858: * \def MBEDTLS_SSL_PROTO_TLS1_3 1885:#define MBEDTLS_SSL_PROTO_TLS1_3 1903: * MBEDTLS_SSL_PROTO_T…

### 11. `Bash`
- **asked:** command=grep -n "error\|#if" ~/ddb-targets/mbedtls/include/mbedtls/check_config.h | grep -i "tls1_3\|PROTO" | head -20
- **got:** 815:#if defined(MBEDTLS_SSL_PROTO_TLS1_3) && \ 820:#error "MBEDTLS_SSL_PROTO_TLS1_3 defined, but not all prerequisites" 823:#if defined(MBEDTLS_SSL_TLS1_3_KEY_EXCHANGE_MODE_EPHEMERAL_ENABLED) 827:#error "MBEDTLS_SSL_TLS1…

### 12. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 1855	#define MBEDTLS_SSL_PROTO_TLS1_2 1856	 1857	/** 1858	 * \def MBEDTLS_SSL_PROTO_TLS1_3 1859	 * 1860	 * Enable support for TLS 1.3. 1861	 * 1862	 * \note See docs/architecture/tls13-support.md for a description of the…

### 13. `Bash`
- **asked:** command=grep -n "define MBEDTLS_SSL_DTLS_SRTP\|define MBEDTLS_SSL_EARLY_DATA\|define MBEDTLS_PSA_CRYPTO_CONFIG\b" ~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 1969://#define MBEDTLS_SSL_EARLY_DATA 2055://#define MBEDTLS_SSL_DTLS_SRTP 2262://#define MBEDTLS_PSA_CRYPTO_CONFIG

### 14. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 1949	 * 1950	 */ 1951	#define MBEDTLS_SSL_TLS1_3_KEY_EXCHANGE_MODE_PSK_EPHEMERAL_ENABLED 1952	 1953	/** 1954	 * \def MBEDTLS_SSL_EARLY_DATA 1955	 * 1956	 * Enable support for RFC 8446 TLS 1.3 early data. 1957	 * 1958	 * …

### 15. `Bash`
- **asked:** command=grep -n "MBEDTLS_SSL_EARLY_DATA" ~/ddb-targets/mbedtls/include/mbedtls/check_config.h
- **got:** 860:#if defined(MBEDTLS_SSL_EARLY_DATA) && \ 864:#error "MBEDTLS_SSL_EARLY_DATA  defined, but not all prerequisites" 867:#if defined(MBEDTLS_SSL_EARLY_DATA) && defined(MBEDTLS_SSL_SRV_C) && \

### 16. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/check_config.h
- **got:** 805	#if defined(MBEDTLS_SHA256_USE_ARMV8_A_CRYPTO_ONLY) && !defined(MBEDTLS_ARCH_IS_ARMV8_A) 806	#error "MBEDTLS_SHA256_USE_ARMV8_A_CRYPTO_ONLY defined on non-Armv8-A system" 807	#endif 808	 809	/* TLS 1.3 requires separ…

**Reasoning.** Now let me check the supported "ways to change" — CMake/Make config flags, config.py, user config file — and the README's build instructions.

### 17. `Bash`
- **asked:** command=grep -n "MBEDTLS_CONFIG_FILE\|MBEDTLS_USER_CONFIG_FILE\|CMake\|## Make\|^## " ~/ddb-targets/mbedtls/README.md | head -40
- **got:** 11:Compiler options can be set using conventional environment variables such as `CC` and `CFLAGS` when using the Make and CMake build system (see below). 36:-   CMake 39:The main systems used for development are CMake an…

### 18. `Bash`
- **asked:** command=sed -n '1,40p' ~/ddb-targets/mbedtls/scripts/config.py
- **got:** #!/usr/bin/env python3  """Mbed TLS and PSA configuration file manipulation library and tool  Basic usage, to read the Mbed TLS configuration:     config = MbedTLSConfig()     if 'MBEDTLS_RSA_C' in config: print('RSA is …

### 19. `Bash`
- **asked:** command=grep -n "add_parser\|'set'\|'unset'\|'get'\|description=" ~/ddb-targets/mbedtls/scripts/config.py | head -30
- **got:** (Bash completed with no output)

### 20. `Bash`
- **asked:** command=grep -n "add_parser\|subparsers\|choices=\[" ~/ddb-targets/mbedtls/framework/scripts/mbedtls_framework/config_common.py 2>/dev/null | head -30 find ~/ddb-targets/mbedtls -iname "config_common.py"
- **got:** (Bash completed with no output)

### 21. `Bash`
- **asked:** command=find ~/ddb-targets/mbedtls -iname "*config_common*" 2>/dev/null grep -n "add_parser\|subcommand\|args.command\|def main" ~/ddb-targets/mbedtls/scripts/config.py | head -30
- **got:** (Bash completed with no output)

### 22. `Bash`
- **asked:** command=wc -l ~/ddb-targets/mbedtls/scripts/config.py; grep -n "add_parser" ~/ddb-targets/mbedtls/scripts/config.py
- **got:** 413 ~/ddb-targets/mbedtls/scripts/config.py

### 23. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/scripts/config.py
- **got:** 350	 351	        if name not in self.settings: 352	            self._get_configfile().templates.append((name, '', '#define ' + name + ' ')) 353	 354	        super().set(name, value) 355	 356	 357	class MbedTLSConfigTool(…

**Reasoning.** That's enough grounding. Let me confirm the `configs/` directory purpose (alternative preset configs) briefly.

### 24. `Bash`
- **asked:** command=ls ~/ddb-targets/mbedtls/configs/ | head -20 sed -n '1,20p' ~/ddb-targets/mbedtls/configs/README.txt 2>/dev/null
- **got:** config-ccm-psk-dtls1_2.h config-ccm-psk-tls1_2.h config-no-entropy.h config-suite-b.h config-symmetric-only.h config-tfm.h config-thread.h crypto-config-ccm-aes-sha256.h ext README.txt This directory contains example con…

**Reasoning.** I have everything needed to answer.

## Answer

**How configuration works — the mechanism**

Mbed TLS is configured entirely at compile time via C preprocessor `#define`/`#undef` macros. There is no runtime feature-flag system. The orchestration point is `include/mbedtls/build_info.h`, which every module includes instead of the config files directly, and which pulls the pieces together in a fixed order (`include/mbedtls/build_info.h:104-192`):

1. Read the base legacy/TLS/X.509 config — `mbedtls/mbedtls_config.h` by default, or `MBEDTLS_CONFIG_FILE` if defined (`include/mbedtls/build_info.h:11

---

## Final answer as submitted

I have everything needed to answer.

## Answer

**How configuration works — the mechanism**

Mbed TLS is configured entirely at compile time via C preprocessor `#define`/`#undef` macros. There is no runtime feature-flag system. The orchestration point is `include/mbedtls/build_info.h`, which every module includes instead of the config files directly, and which pulls the pieces together in a fixed order (`include/mbedtls/build_info.h:104-192`):

1. Read the base legacy/TLS/X.509 config — `mbedtls/mbedtls_config.h` by default, or `MBEDTLS_CONFIG_FILE` if defined (`include/mbedtls/build_info.h:112-116`).
2. Optionally overlay `MBEDTLS_USER_CONFIG_FILE`, explicitly documented as "allow user to override any previous default" (`include/mbedtls/build_info.h:129-131`).
3. If `MBEDTLS_PSA_CRYPTO_CONFIG` is set, read the PSA config — `psa/crypto_config.h` by default or `MBEDTLS_PSA_CRYPTO_CONFIG_FILE`, then an optional `MBEDTLS_PSA_CRYPTO_USER_CONFIG_FILE` overlay (`include/mbedtls/build_info.h:134-143`).
4. Mark `MBEDTLS_CONFIG_FILES_READ` (`include/mbedtls/build_info.h:149`), then run the **adjustment** headers that derive dependent settings and reconcile legacy vs. PSA crypto config: `config_psa.h`, `config_adjust_legacy_crypto.h`, `config_adjust_x509.h`, `config_adjust_ssl.h` (`include/mbedtls/build_info.h:166-183`).
5. Mark `MBEDTLS_CONFIG_IS_FINALIZED` (`include/mbedtls/build_info.h:190`), then include `mbedtls/check_config.h` — the consistency-check pass — as the very last step (`include/mbedtls/build_info.h:192`).

**Where the "off by default" decision is recorded**

Every option lives in `include/mbedtls/mbedtls_config.h` as a `#define NAME` (enabled) or `//#define NAME` (disabled, "comment/uncomment this to enable/disable"). Concrete example: `MBEDTLS_SSL_EARLY_DATA` (RFC 8446 TLS 1.3 early data) is off by default — `//#define MBEDTLS_SSL_EARLY_DATA` at `include/mbedtls/mbedtls_config.h:1969`, with its doc block at `include/mbedtls/mbedtls_config.h:1953-1968` stating the dependency: "Requires: MBEDTLS_SSL_SESSION_TICKETS and either MBEDTLS_SSL_TLS1_3_KEY_EXCHANGE_MODE_PSK_ENABLED or …PSK_EPHEMERAL_ENABLED". PSA-side booleans (`PSA_WANT_xxx`) follow the same on/off-by-comment convention in `include/psa/crypto_config.h`.

**Supported ways to change it**

1. Edit `include/mbedtls/mbedtls_config.h` (or `psa/crypto_config.h`) directly and rebuild.
2. Set `MBEDTLS_CONFIG_FILE` to point at a full replacement config — Mbed TLS ships several presets in `configs/` (e.g. `configs/config-suite-b.h`, `configs/config-thread.h`) documented for exactly this in `configs/README.txt:1-19`, invoked e.g. `CFLAGS="-I$PWD/configs -DMBEDTLS_CONFIG_FILE='<foo.h>'" make`.
3. Set `MBEDTLS_USER_CONFIG_FILE` / `MBEDTLS_PSA_CRYPTO_USER_CONFIG_FILE` to a small overlay file that overrides individual options on top of the base config (`include/mbedtls/build_info.h:124-142`), settable via compiler `-D` flags under Make or CMake (`README.md:11`, `README.md:36-160` for the Make/CMake build systems and `-D`/`CFLAGS` handling).
4. Use `scripts/config.py`, the maintained CLI for reading/writing `mbedtls_config.h` boolean defines and applying bulk presets (`full`, `baremetal`, `crypto`, `crypto_baremetal`, etc. — `scripts/config.py:357-409`) rather than hand-editing.

**What stops a contradictory build**

`include/mbedtls/check_config.h` is included last, after finalization, and is nothing but a long chain of `#if defined(...) && !(...)` / `#error "..."` blocks — a compile-time assertion pass with no runtime cost. For the early-data example: it requires session tickets and a compatible PSK key-exchange mode (`include/mbedtls/check_config.h:860-865`), and separately bounds `MBEDTLS_SSL_MAX_EARLY_DATA_SIZE` to `0..UINT32_MAX` (`include/mbedtls/check_config.h:867-872`). Other examples in the same file: TLS 1.3 requires HKDF + a hash algorithm from PSA (`include/mbedtls/check_config.h:815-821`) and `MBEDTLS_SSL_KEEP_PEER_CERTIFICATE` (`include/mbedtls/check_config.h:840-842`); enabling any TLS protocol version without a key-exchange method is rejected (`include/mbedtls/check_config.h:844-858`). Because this file is included only after every config source (base file, user overlay, PSA config, adjustment headers) has been merged, it is the single place that sees the final, combined configuration and fails the build with a named `#error` the moment two options conflict — it can't be bypassed by any of the four configuration methods above since they all funnel through `build_info.h`.

## Gaps

- The doxyguard-db index (`dossier`/`search`) does not cover file-level `#define`/`#if` content in headers — it resolved file paths via prose search but returned "not indexed" for `dossier` lookups on `mbedtls_config.h`/`check_config.h` (these are config macros, not functions/classes it tracks as symbols). I fell back to reading the source directly for all mechanism and line-number detail above.
- I did not exhaustively enumerate `check_config.h` (it is long); the examples cited are representative, not a complete list of every cross-option constraint.
- I did not verify CMake's exact `-D` option name for setting `MBEDTLS_CONFIG_FILE` (README points to `cmake -LH` to list options, which I didn't run) — Make's `CFLAGS=` route is confirmed directly from `configs/README.txt`.
