# Q11 — src — haiku — run 1

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
