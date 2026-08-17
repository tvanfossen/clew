# Q11 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=cd ~/ddb-targets/mbedtls && find . -type f -name "CMakeLists.txt" -o -name "config.h" -o -name "*.cmake" | head -20
- **got:** ./pkgconfig/JoinPaths.cmake ./pkgconfig/CMakeLists.txt ./tests/CMakeLists.txt ./3rdparty/everest/CMakeLists.txt ./3rdparty/p256-m/CMakeLists.txt ./3rdparty/CMakeLists.txt ./programs/ssl/CMakeLists.txt ./programs/pkey/CMa…

### 2. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls
- **got ⚠ error:** EISDIR: illegal operation on a directory, read '~/ddb-targets/mbedtls'

### 3. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/CMakeLists.txt
- **got:** 1	# 2	# CMake build system design considerations: 3	# 4	# - Include directories: 5	#   + Do not define include directories globally using the include_directories 6	#     command but rather at the target level using the 7…

### 4. `Bash`
- **asked:** command=find . -name "*config.h" | head -20
- **got:** ./configs/ext/mbedtls_entropy_nv_seed_config.h ./library/check_crypto_config.h ./include/psa/crypto_config.h ./include/mbedtls/mbedtls_config.h ./include/mbedtls/check_config.h

### 5. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/mbedtls_config.h
- **got:** 1	/** 2	 * \file mbedtls_config.h 3	 * 4	 * \brief Configuration options (set of defines) 5	 * 6	 *  This set of compile-time options may be used to enable 7	 *  or disable features selectively, and reduce the global 8	 …

### 6. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/check_config.h
- **got:** 1	/** 2	 * \file check_config.h 3	 * 4	 * \brief Consistency checks for configuration options 5	 * 6	 * This is an internal header. Do not include it directly. 7	 * 8	 * This header is included automatically by all publi…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/scripts/config.py
- **got:** 1	#!/usr/bin/env python3 2	 3	"""Mbed TLS and PSA configuration file manipulation library and tool 4	 5	Basic usage, to read the Mbed TLS configuration: 6	    config = MbedTLSConfig() 7	    if 'MBEDTLS_RSA_C' in config: …

### 8. `Bash`
- **asked:** command=find . -name "build_info.h" -o -name "config_adjust*"
- **got:** ./include/psa/build_info.h ./include/mbedtls/build_info.h ./include/mbedtls/config_adjust_x509.h ./include/mbedtls/config_adjust_ssl.h ./include/mbedtls/config_adjust_legacy_crypto.h ./include/mbedtls/config_adjust_legac…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/build_info.h
- **got:** 1	/** 2	 * \file mbedtls/build_info.h 3	 * 4	 * \brief Build-time configuration info 5	 * 6	 *  Include this file if you need to depend on the 7	 *  configuration options defined in mbedtls_config.h or MBEDTLS_CONFIG_FIL…

### 10. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/build_info.h
- **got:** 150	 151	/* Auto-enable MBEDTLS_CTR_DRBG_USE_128_BIT_KEY if 152	 * MBEDTLS_AES_ONLY_128_BIT_KEY_LENGTH and MBEDTLS_CTR_DRBG_C defined 153	 * to ensure a 128-bit key size in CTR_DRBG. 154	 */ 155	#if defined(MBEDTLS_AES_O…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/config_adjust_legacy_crypto.h
- **got:** 1	/** 2	 * \file mbedtls/config_adjust_legacy_crypto.h 3	 * \brief Adjust legacy configuration configuration 4	 * 5	 * This is an internal header. Do not include it directly. 6	 * 7	 * Automatically enable certain depend…

### 12. `Bash`
- **asked:** command=find . -path "./configs/*" -name "*.h" | head -10
- **got:** ./configs/config-symmetric-only.h ./configs/config-ccm-psk-dtls1_2.h ./configs/config-no-entropy.h ./configs/config-ccm-psk-tls1_2.h ./configs/config-tfm.h ./configs/ext/tfm_mbedcrypto_config_profile_medium.h ./configs/e…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/configs/config-symmetric-only.h
- **got:** 1	/** 2	 * \file config-symmetric-only.h 3	 * 4	 * \brief Configuration without any asymmetric cryptography. 5	 */ 6	/* 7	 *  Copyright The Mbed TLS Contributors 8	 *  SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-la…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/include/mbedtls/check_config.h
- **got:** 150	 151	#if defined(MBEDTLS_ECDH_C) && !defined(MBEDTLS_ECP_C) 152	#error "MBEDTLS_ECDH_C defined, but not all prerequisites" 153	#endif 154	 155	#if defined(MBEDTLS_ECDSA_C) &&            \ 156	    ( !defined(MBEDTLS_E…

### 15. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/CMakeLists.txt
- **got:** 1	option(USE_STATIC_MBEDTLS_LIBRARY "Build Mbed TLS static library." ON) 2	option(USE_SHARED_MBEDTLS_LIBRARY "Build Mbed TLS shared library." OFF) 3	option(LINK_WITH_PTHREAD "Explicitly link Mbed TLS library to pthread."…

### 16. `Bash`
- **asked:** command=grep -n "MBEDTLS_CONFIG_FILE\|target_compile_definitions" library/CMakeLists.txt | head -20
- **got:** 356:    # Pass-through MBEDTLS_CONFIG_FILE and MBEDTLS_USER_CONFIG_FILE 357:    if(MBEDTLS_CONFIG_FILE) 358:        target_compile_definitions(${target} 359:            PUBLIC MBEDTLS_CONFIG_FILE="${MBEDTLS_CONFIG_FILE}"…

### 17. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/library/CMakeLists.txt
- **got:** 350	    target_include_directories(${target} 351	        PUBLIC $<BUILD_INTERFACE:${MBEDTLS_DIR}/include/> 352	               $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}> 353	        PRIVATE ${MBEDTLS_DIR}/library/ 3…

### 18. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/scripts/config.py
- **got:** 150	# need to be repeated here. 151	EXCLUDE_FROM_BAREMETAL = frozenset([ 152	    #pylint: disable=line-too-long 153	    'MBEDTLS_ENTROPY_NV_SEED', # requires a filesystem and FS_IO or alternate NV seed hooks 154	    'MBE…

### 19. `Bash`
- **asked:** command=find . -name "README*" -o -name "QUICKSTART*" | head -5
- **got:** ./tests/git-scripts/README.md ./docs/proposed/README ./README.md ./3rdparty/everest/README.md ./3rdparty/p256-m/README.md

### 20. `Bash`
- **asked:** command=head -100 README.md | grep -i "config\|feature"
- **got:** Configuration Mbed TLS should build out of the box on most systems. Some platform specific options are available in the fully documented configuration file `include/mbedtls/mbedtls_config.h`, which is also the place wher…

### 21. `Read`
- **asked:** file_path=~/ddb-targets/mbedtls/configs/README.txt
- **got:** 1	This directory contains example configuration files. 2	 3	The examples are generally focused on a particular usage case (eg, support for 4	a restricted number of ciphersuites) and aim at minimizing resource usage for 5…

**Reasoning.** ## How Mbedtls is Configured

This library uses **C preprocessor defines** for configuration. Each feature is enabled/disabled by defining a `#define` macro, which are collected into header files that the compiler processes before compilation.

### Where Configuration Decisions Are Recorded

**Primary config file:** `include/mbedtls/mbedtls_config.h:1-22` — The main configuration file where most compile-time options are defined as preprocessor macros.

**Secondary config:** `include/psa/crypto_config.h` — Separate configuration for PSA Crypto API options.

**User override:** `MBEDTLS_USER_CONF

---

## Final answer as submitted

## How Mbedtls is Configured

This library uses **C preprocessor defines** for configuration. Each feature is enabled/disabled by defining a `#define` macro, which are collected into header files that the compiler processes before compilation.

### Where Configuration Decisions Are Recorded

**Primary config file:** `include/mbedtls/mbedtls_config.h:1-22` — The main configuration file where most compile-time options are defined as preprocessor macros.

**Secondary config:** `include/psa/crypto_config.h` — Separate configuration for PSA Crypto API options.

**User override:** `MBEDTLS_USER_CONFIG_FILE` — An optional additional file appended after the main config, allowing users to override or supplement defaults without modifying the shipped config.

### Configuration Initialization Sequence

The configuration flow is defined in `include/mbedtls/build_info.h:104-192`:

1. **Load primary config** (lines 112-116): Either `mbedtls_config.h` or a custom file specified via `MBEDTLS_CONFIG_FILE` CMake variable
2. **Load user config** (lines 129-131): Append `MBEDTLS_USER_CONFIG_FILE` if provided
3. **Load PSA crypto config** (lines 134-142): If `MBEDTLS_PSA_CRYPTO_CONFIG` is defined
4. **Mark files read** (line 149): Set `MBEDTLS_CONFIG_FILES_READ` to signal configuration phase complete
5. **Auto-enable dependencies** (lines 151-177): Automatically enable required symbols based on what's already enabled
6. **Adjust for legacy compatibility** (lines 179-183): Include multiple `config_adjust_*.h` files
7. **Finalize configuration** (line 190): Set `MBEDTLS_CONFIG_IS_FINALIZED`
8. **Validate configuration** (line 192): Include `check_config.h` which performs compile-time validation

### Supported Ways to Change Configuration

**1. Direct file editing** (`configs/README.txt:10`)
- Edit `include/mbedtls/mbedtls_config.h` directly

**2. CMake options** (`CMakeLists.txt:147-148`):
```cmake
set(MBEDTLS_CONFIG_FILE "" CACHE FILEPATH "Mbed TLS config file (overrides default).")
set(MBEDTLS_USER_CONFIG_FILE "" CACHE FILEPATH "Mbed TLS user config file (appended to default).")
```

Users can pass these to cmake: `cmake -DMBEDTLS_CONFIG_FILE=/path/to/config.h`

**3. Build flags** (`configs/README.txt:12-20`)
- Use compiler preprocessor flags: `-DMBEDTLS_CONFIG_FILE='<foo.h>'` with `-I` to add include paths

**4. Python configuration tool** (`scripts/config.py:357-413`)
- `scripts/config.py` provides programmatic manipulation with pre-defined profiles:
  - `full` / `full_no_deprecated` / `full_no_platform` / `crypto_full` / `crypto_baremetal` / `baremetal`
- Example: `python3 scripts/config.py set MBEDTLS_AES_C`

**5. Pre-built example configs** (`configs/*.h`)
- Use any of the pre-configured files in `configs/` as a base (e.g., `config-symmetric-only.h:1`)

### What Prevents Contradictory Configuration

**1. Compile-time validation checks** (`include/mbedtls/check_config.h`)

The entire file is a set of `#if` / `#error` directives. Examples at lines 101-149:
- `MBEDTLS_CTR_DRBG_C` requires `MBEDTLS_AES_C` or PSA equivalents (lines 101-105)
- `MBEDTLS_BLOCK_CIPHER_NO_DECRYPT` conflicts with `MBEDTLS_CIPHER_MODE_CBC`, `MBEDTLS_CIPHER_MODE_XTS`, `MBEDTLS_DES_C`, `MBEDTLS_NIST_KW_C` (lines 136-149)
- `MBEDTLS_CHACHAPOLY_C` requires both `MBEDTLS_CHACHA20_C` AND `MBEDTLS_POLY1305_C` (lines 267-273)

If contradictions exist, the compiler stops with a clear `#error` message. There is **no way** to produce a binary with contradictory options — compilation will fail.

**2. Automatic dependency activation** (`include/mbedtls/config_adjust_legacy_crypto.h:94-136`)

When a feature is enabled that depends on others, those dependencies are **automatically enabled**:
- If `MBEDTLS_PSA_CRYPTO_C` is defined, `MBEDTLS_PSA_CRYPTO_CLIENT` is automatically defined (lines 97-99)
- If `MBEDTLS_MD_C` is defined, `MBEDTLS_MD_LIGHT` is automatically defined (lines 119-121)
- If `MBEDTLS_ECJPAKE_C`, `MBEDTLS_PEM_PARSE_C`, or several others are defined, `MBEDTLS_MD_LIGHT` is auto-enabled (lines 126-136)

This means users cannot create a state where a feature is enabled but its dependencies are missing.

**3. Mutual exclusion checks in validation** (`check_config.h:121-134`)

Some options are explicitly forbidden from coexisting. Example (lines 121-134):
- `MBEDTLS_BLOCK_CIPHER_NO_DECRYPT` cannot coexist with `PSA_WANT_ALG_CBC_NO_PADDING`, `PSA_WANT_ALG_CBC_PKCS7`, `PSA_WANT_ALG_ECB_NO_PADDING`, or `PSA_WANT_KEY_TYPE_DES`

**4. Serialized initialization order** (`build_info.h` lines 104-192)

The configuration files are read in a strict order with clear barriers:
- All config files read → dependencies auto-enabled → legacy adjustments applied → finalization flag set → validation runs

This ensures every dependency is resolved before validation, so no valid configuration can be broken by the ordering.

**5. Python script validation** (`scripts/config.py:140-145`, `345-354`)

The `config.py` script knows which options are in conflict (`EXCLUDE_FROM_FULL`, lines 71-108) and handles them when generating profiles. For example, `MBEDTLS_BLOCK_CIPHER_NO_DECRYPT` is in `EXCLUDE_FROM_FULL` because it conflicts with other enabled features.

## Gaps

- I did not find explicit documentation of a comprehensive dependency map in a single machine-readable file (though the rules are encoded in `check_config.h` as C preprocessor directives)
- The exact token patterns recognized by the `scripts/config.py` tool's parsing are in the parent `config_common` module which is imported but not in this repo
- I did not verify whether CMake itself performs any additional validation of the configuration options (only that it passes them through to the compiler)
