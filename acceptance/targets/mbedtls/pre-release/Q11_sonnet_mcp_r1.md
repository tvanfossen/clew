# Q11 — mcp — sonnet — run 1

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
