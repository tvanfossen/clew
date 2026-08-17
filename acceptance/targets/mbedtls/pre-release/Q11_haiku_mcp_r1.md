# Q11 — mcp — haiku — run 1

## Answer

**How mbedtls is configured:**

Mbedtls uses compile-time preprocessor macros to configure which features are enabled or disabled. The library is configured entirely at build time through C preprocessor `#define` symbols, with no runtime configuration mechanism. Configuration decisions are recorded in header files as boolean enables (a feature is on if the macro is defined, off if not).

**Where decisions are recorded:**

Configuration decisions are primarily recorded in three places:

1. **Default configuration file**: `include/mbedtls/mbedtls_config.h` — This is the primary file containing all feature toggles. Each feature like `MBEDTLS_RSA_C`, `MBEDTLS_SSL_TLS_C`, `MBEDTLS_AES_C`, etc., is defined here (or commented out). The file includes extensive documentation for each option explaining what it enables, what it requires, and what requires it.

2. **PSA crypto configuration**: `include/psa/crypto_config.h` — When `MBEDTLS_PSA_CRYPTO_CONFIG` is enabled, PSA-specific features are configured separately using `PSA_WANT_*` symbols.

3. **Build-time integration**: `include/mbedtls/build_info.h` — This file orchestrates the configuration loading sequence. It includes the main config file (or an override), then user config files, then applies automatic adjustments. The sequence is (`include/mbedtls/build_info.h:112-192`):
   - Load `MBEDTLS_CONFIG_FILE` if defined, else load default `mbedtls_config.h`
   - Load `MBEDTLS_USER_CONFIG_FILE` if defined (allows per-application overrides)
   - Load PSA config files if PSA crypto is enabled
   - Include auto-adjustment files (`config_adjust_legacy_crypto.h`, `config_adjust_x509.h`, `config_adjust_ssl.h`)
   - Finally, include `check_config.h` for consistency validation

**Supported ways to change configuration:**

1. **Direct file editing**: Edit `include/mbedtls/mbedtls_config.h` by uncommenting/commenting feature lines.

2. **CMake build options** (`CMakeLists.txt:147-148`):
   - `-DMBEDTLS_CONFIG_FILE=<path>` — Override the entire config file with a custom one
   - `-DMBEDTLS_USER_CONFIG_FILE=<path>` — Append/override specific settings on top of the default config

3. **Python configuration tool**: `scripts/config.py` provides programmatic access to manipulate configuration files. It can read, enable, disable, and generate configurations (`scripts/config.py:1-8`):
   ```
   config = MbedTLSConfig()
   if 'MBEDTLS_RSA_C' in config: ...  # read
   ```

4. **Pre-built configuration profiles**: The `configs/` directory contains pre-configured profiles for specific use cases (e.g., `config-ccm-psk-dtls1_2.h`, `config-symmetric-only.h`).

**What prevents contradictory configurations:**

Two mechanisms enforce consistency:

1. **Automatic dependency injection** via auto-adjustment files. For example, `config_adjust_legacy_crypto.h:97-99` automatically enables `MBEDTLS_PSA_CRYPTO_CLIENT` if `MBEDTLS_PSA_CRYPTO_C` is defined. This ensures dependent features are implicitly enabled when their requirements are enabled.

2. **Compile-time error checks in `include/mbedtls/check_config.h`**. This file contains `#error` preprocessor directives that fire at compilation time if incompatible options are set. Examples include (`check_config.h:57-59`, `121-149`):
   - `#error "MBEDTLS_HAVE_TIME_DATE without MBEDTLS_HAVE_TIME does not make sense"`
   - `#error "MBEDTLS_CTR_DRBG_C defined, but not all prerequisites"` (when required dependencies are missing)
   - `#error "... MBEDTLS_BLOCK_CIPHER_NO_DECRYPT and MBEDTLS_CIPHER_MODE_CBC cannot be defined simultaneously"`

These checks are enforced **after all configuration files have been loaded and dependencies auto-adjusted** — once `MBEDTLS_CONFIG_IS_FINALIZED` is defined (`build_info.h:190`), then `check_config.h` is included to validate the final configuration state (`build_info.h:192`).

## Gaps

I could not locate the complete list of all available MBEDTLS feature flags from the index (the search returned only patterns and specific examples), nor a machine-readable manifest of which features depend on which others. The `check_config.h` file contains the constraints, but a structured dependency graph would require reading that entire file or parsing the doxygen comments in `mbedtls_config.h`.
