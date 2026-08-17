# Q11 — src — sonnet — run 1

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
