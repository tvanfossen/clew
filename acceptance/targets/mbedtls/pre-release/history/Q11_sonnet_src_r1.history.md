# Q11 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=cd ~/ddb-targets/mbedtls && find . -iname "*config*.h" -not -path "*/tests/*" | head -50
- **got:** ./configs/config-symmetric-only.h ./configs/config-ccm-psk-dtls1_2.h ./configs/config-no-entropy.h ./configs/config-ccm-psk-tls1_2.h ./configs/config-tfm.h ./configs/ext/tfm_mbedcrypto_config_profile_medium.h ./configs/e…

### 2. `Bash`
- **asked:** command=ls include/mbedtls/ | grep -i config; echo ---; ls scripts/ 2>/dev/null | grep -i config; echo ---; find . -iname "check_config.h"
- **got:** check_config.h config_adjust_legacy_crypto.h config_adjust_legacy_from_psa.h config_adjust_psa_from_legacy.h config_adjust_psa_superset_legacy.h config_adjust_ssl.h config_adjust_x509.h config_psa.h mbedtls_config.h --- …

### 3. `Bash`
- **asked:** command=sed -n '1,80p' include/mbedtls/mbedtls_config.h
- **got:** /**  * \file mbedtls_config.h  *  * \brief Configuration options (set of defines)  *  *  This set of compile-time options may be used to enable  *  or disable features selectively, and reduce the global  *  memory footpr…

### 4. `Bash`
- **asked:** command=grep -n "MBEDTLS_SSL_RENEGOTIATION\|MBEDTLS_HAVE_SSE2\|off by default\|is not set by default\|disabled by default" include/mbedtls/mbedtls_config.h | head -30
- **got:** 105: * \def MBEDTLS_HAVE_SSE2 111://#define MBEDTLS_HAVE_SSE2 1114: * might still happen. For this reason, this is disabled by default. 1795: * \def MBEDTLS_SSL_RENEGOTIATION 1816:#define MBEDTLS_SSL_RENEGOTIATION

### 5. `Bash`
- **asked:** command=sed -n '1,60p' include/mbedtls/check_config.h
- **got:** /**  * \file check_config.h  *  * \brief Consistency checks for configuration options  *  * This is an internal header. Do not include it directly.  *  * This header is included automatically by all public Mbed TLS heade…

### 6. `Bash`
- **asked:** command=grep -n "error\|#if" include/mbedtls/check_config.h | head -60
### 7. `Bash`
- **asked:** command=sed -n '1,50p' scripts/config.py
- **got:** 18:#ifndef MBEDTLS_CHECK_CONFIG_H 23:#if !defined(MBEDTLS_CONFIG_IS_FINALIZED) 25:         "This may cause spurious errors. " \ 34:#if CHAR_BIT != 8 35:#error "Mbed TLS requires a platform with 8-bit chars" 40:#if define…

- **got:** #!/usr/bin/env python3  """Mbed TLS and PSA configuration file manipulation library and tool  Basic usage, to read the Mbed TLS configuration:     config = MbedTLSConfig()     if 'MBEDTLS_RSA_C' in config: print('RSA is …

### 8. `Bash`
- **asked:** command=grep -n "build_info.h\|MBEDTLS_CONFIG_FILE\|MBEDTLS_USER_CONFIG_FILE\|MBEDTLS_CONFIG_IS_FINALIZED" include/mbedtls/build_info.h | head -40
- **got:** 2: * \file mbedtls/build_info.h 7: *  configuration options defined in mbedtls_config.h or MBEDTLS_CONFIG_FILE 104:#if defined(MBEDTLS_CONFIG_FILES_READ) 105:#error "Something went wrong: MBEDTLS_CONFIG_FILES_READ define…

### 9. `Bash`
- **asked:** command=grep -n "MBEDTLS_CONFIG_FILE\|MBEDTLS_USER_CONFIG_FILE" CMakeLists.txt library/CMakeLists.txt 2>/dev/null
- **got:** CMakeLists.txt:146:# Make MBEDTLS_CONFIG_FILE and MBEDTLS_USER_CONFIG_FILE into PATHs CMakeLists.txt:147:set(MBEDTLS_CONFIG_FILE "" CACHE FILEPATH "Mbed TLS config file (overrides default).") CMakeLists.txt:148:set(MBEDT…

### 10. `Bash`
- **asked:** command=grep -n "MBEDTLS_ECP_RESTARTABLE\|MBEDTLS_SSL_DTLS_SRTP" include/mbedtls/mbedtls_config.h
- **got:** 787: * \def MBEDTLS_ECP_RESTARTABLE 839://#define MBEDTLS_ECP_RESTARTABLE 2027: * \def MBEDTLS_SSL_DTLS_SRTP 2055://#define MBEDTLS_SSL_DTLS_SRTP

### 11. `Bash`
- **asked:** command=sed -n '787,842p' include/mbedtls/mbedtls_config.h
- **got:** * \def MBEDTLS_ECP_RESTARTABLE  *  * Enable "non-blocking" ECC operations that can return early and be resumed.  *  * This allows various functions to pause by returning  * #MBEDTLS_ERR_ECP_IN_PROGRESS (or, for functions…

### 12. `Bash`
- **asked:** command=sed -n '185,200p' include/mbedtls/check_config.h
- **got:** #endif  #if defined(MBEDTLS_ECP_RESTARTABLE)           && \     ( defined(MBEDTLS_ECDH_COMPUTE_SHARED_ALT) || \       defined(MBEDTLS_ECDH_GEN_PUBLIC_ALT)     || \       defined(MBEDTLS_ECDSA_SIGN_ALT)          || \     …

### 13. `Bash`
- **asked:** command=grep -n "def set\|def unset\|def adapt\|class MbedTLSConfig\|def __init__" scripts/config.py | head -30
- **got:** 268:class MbedTLSConfigFile(config_common.ConfigFile): 279:    def __init__(self, filename=None): 298:    def __init__(self, filename=None): 302:class MbedTLSConfig(config_common.Config): 309:    def __init__(self, filen…

**Reasoning.** Now let's check config.py CLI usage and the CMake config-file behavior for finalization, plus check_config.h is auto-included via build_info.h.

### 14. `Bash`
- **asked:** command=sed -n '90,200p' include/mbedtls/build_info.h
- **got:** #define MBEDTLS_GCC_VERSION \     (__GNUC__ * 10000 + __GNUC_MINOR__ * 100 + __GNUC_PATCHLEVEL__) #endif  #if defined(_MSC_VER) && !defined(_CRT_SECURE_NO_DEPRECATE) #define _CRT_SECURE_NO_DEPRECATE 1 #endif  /* Define `…

### 15. `Bash`
- **asked:** command=grep -n "set-all\|full\|baremetal\|unset\b\|get\b\|def main\|add_argument\|subparsers" scripts/config.py | head -40
- **got:** 40:def realfull_adapter(_name, _value, _active): 63:# The goal of the full configuration is to have everything that can be tested 111:    """Whether the xxx_ALT symbol should be included in the full configuration. 132:de…

### 16. `Bash`
- **asked:** command=grep -n "add_parser\|def main\|'set'\|'unset'\|'get'\|'adapt'" scripts/mbedtls_framework/config_common.py | head -40
- **got:** grep: scripts/mbedtls_framework/config_common.py: No such file or directory

### 17. `Bash`
- **asked:** command=find . -name "config_common.py"; echo ---; grep -n "add_parser\|def main\|command ==" $(find . -name config_common.py) | head -50
- **got:** ---

### 18. `Bash`
- **asked:** command=find / -name "config_common.py" 2>/dev/null
- **got:** ~/esp/esp-idf/components/mbedtls/mbedtls/framework/scripts/mbedtls_framework/config_common.py ~/esp/esp-idf/components/openthread/openthread/third_party/mbedtls/repo/framework/scripts/mbedtls_framework/config_common.py

### 19. `Bash`
- **asked:** command=ls framework 2>/dev/null; cat .gitmodules 2>/dev/null; find . -maxdepth 2 -iname "framework*"
- **got:** [submodule "framework"] 	path = framework 	url = https://github.com/Mbed-TLS/mbedtls-framework ./scripts/framework_scripts_path.py ./framework

### 20. `Bash`
- **asked:** command=ls framework/ 2>/dev/null | head; ls framework/scripts/mbedtls_framework/ 2>/dev/null
- **got ⚠ error:** Exit code 2

### 21. `Bash`
- **asked:** command=sed -n '357,470p' scripts/config.py
- **got:** class MbedTLSConfigTool(config_common.ConfigTool):     """Command line mbedtls_config.h and crypto_config.h manipulation tool."""      def __init__(self):         super().__init__(MbedTLSConfigFile.default_path)         …

### 22. `Bash`
- **asked:** command=grep -rn "config.py" docs/ *.md 2>/dev/null | head -30
- **got:** docs/architecture/psa-migration/testing.md:13:ensured by the fact that `scripts/config.py full` enables docs/architecture/psa-migration/outcome-analysis.sh:60:scripts/config.py full docs/architecture/psa-migration/outcom…

### 23. `Bash`
- **asked:** command=grep -n "config.py\|MBEDTLS_CONFIG_FILE\|mbedtls_config.h" README.md 2>/dev/null | head -30
- **got:** 9:Mbed TLS should build out of the box on most systems. Some platform specific options are available in the fully documented configuration file `include/mbedtls/mbedtls_config.h`, which is also the place where features c…

**Reasoning.** Good, this confirms the `config.py set NAME` usage. Now let's check the CMake option for MBEDTLS_CONFIG_FILE precedence and Makefile behavior, plus check where the "finalized" enforcement / prerequisite errors show a concrete contradiction example being caught at compile-time.

### 24. `Bash`
- **asked:** command=sed -n '140,160p' CMakeLists.txt
- **got:** if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)     set(CMAKE_BUILD_TYPE ${CMAKE_BUILD_TYPE}         CACHE STRING "Choose the type of build: None Debug Release Coverage ASan ASanDbg MemSan MemSanDbg Check CheckFul…

### 25. `Bash`
- **asked:** command=grep -n "MBEDTLS_CONFIG_FILE\|MBEDTLS_USER_CONFIG_FILE" Makefile 2>/dev/null | head -20
- **got:** (Bash completed with no output)

**Reasoning.** I have everything needed. Let me verify a plain Makefile exists and how it compiles (to confirm CFLAGS pass-through isn't the main mechanism, since config is header-based).

### 26. `Bash`
- **asked:** command=ls Makefile 2>/dev/null && grep -n "^CFLAGS\|DMBEDTLS_CONFIG" Makefile | head -10
- **got:** Makefile

**Reasoning.** Now I have enough to write the full answer.

## Answer

**How configuration works (compile-time, header-based, not a build-system flag list)**

Mbed TLS's feature set is controlled by C preprocessor macros defined in a single header, `include/mbedtls/mbedtls_config.h`. Each optional feature is a commented-out `#define`; leaving the `//` in place means "off by default", removing it means "on". Example — restartable (non-blocking) ECC operations, off by default:

- Doxygen block documents the feature and its dependency (`include/mbedtls/mbedtls_config.h:787-838`)
- The actual off-by-default line

---

## Final answer as submitted

Now I have enough to write the full answer.

## Answer

**How configuration works (compile-time, header-based, not a build-system flag list)**

Mbed TLS's feature set is controlled by C preprocessor macros defined in a single header, `include/mbedtls/mbedtls_config.h`. Each optional feature is a commented-out `#define`; leaving the `//` in place means "off by default", removing it means "on". Example — restartable (non-blocking) ECC operations, off by default:

- Doxygen block documents the feature and its dependency (`include/mbedtls/mbedtls_config.h:787-838`)
- The actual off-by-default line: `//#define MBEDTLS_ECP_RESTARTABLE` (`include/mbedtls/mbedtls_config.h:839`)

**Where the "off by default" decision is recorded**

Directly in that file, as the presence/absence of the `#define`. There is no separate defaults database — the header *is* the record. `README.md:9` states this explicitly: "Some platform specific options are available in the fully documented configuration file `include/mbedtls/mbedtls_config.h`, which is also the place where features can be selected."

**Supported ways to change it**

1. **Edit `mbedtls_config.h` directly** — uncomment the `#define` (README.md:9).
2. **`scripts/config.py`** — a Python tool that edits the config header programmatically, e.g. `python3 scripts/config.py set MBEDTLS_PSA_P256M_DRIVER_ENABLED` (`docs/psa-driver-example-and-guide.md:145-146`). It also supports named "adapter" presets such as `full`, `baremetal`, `crypto`, etc., which flip whole groups of options at once (`scripts/config.py:367-407`).
3. **`MBEDTLS_CONFIG_FILE`** — a compile-time macro (set via `-D` or CMake cache var) that replaces `mbedtls_config.h` entirely with a different file (`include/mbedtls/build_info.h:112-115`; CMake wiring: `CMakeLists.txt:147`, `library/CMakeLists.txt:357-359`). Shipped example alternates live under `configs/` (e.g. `configs/config-thread.h`, `configs/config-suite-b.h`).
4. **`MBEDTLS_USER_CONFIG_FILE`** — a second compile-time macro for a file that is included *after* the base config, to override/append individual settings without replacing the whole file (`include/mbedtls/build_info.h:126-131`; CMake wiring: `CMakeLists.txt:148`, `438-442`). This is the documented preferred route for small project-specific tweaks (`docs/psa-driver-example-and-guide.md:137`).
5. Separately, if `MBEDTLS_PSA_CRYPTO_CONFIG` is enabled, PSA's own `PSA_WANT_xxx` macros are configured the same way via `psa/crypto_config.h`, with matching `MBEDTLS_PSA_CRYPTO_CONFIG_FILE` / `MBEDTLS_PSA_CRYPTO_USER_CONFIG_FILE` override points (`include/mbedtls/build_info.h:132-138`).

All of these funnel through the same inclusion sequence in `include/mbedtls/build_info.h:112-138`, which every public Mbed TLS header pulls in.

**What stops a build whose options contradict each other**

After all config files are read, `build_info.h` runs derived/adjustment headers (`config_psa.h`, `config_adjust_legacy_crypto.h`, `config_adjust_x509.h`, `config_adjust_ssl.h`) and then defines `MBEDTLS_CONFIG_IS_FINALIZED` before including `include/mbedtls/check_config.h` (`include/mbedtls/build_info.h:149-190`). `check_config.h` is a large set of `#if defined(...) ... #error "..."` preprocessor checks that enforce prerequisites and mutual exclusions, e.g.:

- Missing dependency: `#if defined(MBEDTLS_HAVE_TIME_DATE) && !defined(MBEDTLS_HAVE_TIME) / #error "... does not make sense"` (`include/mbedtls/check_config.h:57-58`)
- Missing dependency: `#if defined(MBEDTLS_CTR_DRBG_C) && !(...) / #error "MBEDTLS_CTR_DRBG_C defined, but not all prerequisites"` (`include/mbedtls/check_config.h:101-104`)
- Direct contradiction between two enabled options: `#if defined(MBEDTLS_BLOCK_CIPHER_NO_DECRYPT) && defined(PSA_WANT_ALG_CBC_NO_PADDING) / #error "... cannot be defined simultaneously"` (`include/mbedtls/check_config.h:121-126`)
- Specific to the example feature above: enabling `MBEDTLS_ECP_RESTARTABLE` together with any `*_ALT` implementation fails: `#if defined(MBEDTLS_ECP_RESTARTABLE) && (defined(MBEDTLS_ECDH_COMPUTE_SHARED_ALT) || ... || defined(MBEDTLS_ECP_ALT)) / #error "MBEDTLS_ECP_RESTARTABLE defined, but it cannot coexist with an alternative ECP implementation"` (`include/mbedtls/check_config.h:187-195`), matching the doc note that this feature "is incompatible with MBEDTLS_ECP_ALT, MBEDTLS_ECDH_XXX_ALT, MBEDTLS_ECDSA_XXX_ALT" (`include/mbedtls/mbedtls_config.h:829-831`).

These are hard compile errors (`#error`), so a contradictory configuration fails at preprocessing time for every translation unit, regardless of which of the four override mechanisms produced it — the check runs once, centrally, after all config sources have been merged (`include/mbedtls/build_info.h:149-190` → `check_config.h`). The header explicitly warns not to include `check_config.h` directly or from a config file, since it depends on `MBEDTLS_CONFIG_IS_FINALIZED` having been set after all adjustment passes (`include/mbedtls/check_config.h:8-11, 23-27`).

## Gaps

- `scripts/config.py`'s base class (`config_common.ConfigTool`/`ConfigFile`, imported via `framework_scripts_path.py`) lives in the `framework` git submodule, which is not checked out in this working copy (`ls framework/` is empty). So I could not inspect the exact `get`/`set`/`unset`/`adapt` CLI grammar in its own source — I relied on the documented example invocation (`docs/psa-driver-example-and-guide.md:145-146`) and the subclass's adapter registrations in `scripts/config.py:357-407` rather than the base parser itself.
- I did not exhaustively enumerate every `#error` in `check_config.h` (it's several hundred lines); I cited representative dependency/contradiction checks, including the one specific to the example feature (`MBEDTLS_ECP_RESTARTABLE`).
