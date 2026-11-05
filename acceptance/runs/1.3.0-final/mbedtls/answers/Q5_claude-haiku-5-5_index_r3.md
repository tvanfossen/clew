## Short answer

Constant time here is a coding discipline plus a best-effort compiler barrier. Nothing in the build proves it. The `mbedtls_ct_*` helpers build branch-free bit-mask arithmetic, and inline assembly hides values from the optimizer on four architectures. On any other compiler, the helpers fall back to plain C without any warning. Verification is a test-time check with Valgrind or MemorySanitizer, and it only covers paths the tests exercise. The facility is used across about 35 library files, but it is not uniform, and some code, such as `ecp.c`, does not use it directly.

## How it is enforced at the instruction level

The primitives live in `library/constant_time_impl.h`:

1. **Branch-free masks.** `mbedtls_ct_bool(x)` (`constant_time_impl.h:120`) maps any value to all-ones (non-zero input) or all-zeros (zero input). On x86-64 it is `mov / neg / or / sar $63`, so no branch and no flag-dependent instruction.
2. **Optimizer barrier.** `mbedtls_ct_compiler_opaque` (`:85`) is `asm volatile("" : "+r"(x))`. The empty asm forces the compiler to treat `x` as unknown, so it cannot fold a secret-derived value back into a branch. The C fallback is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero defined in `library/constant_time.c:29`.
3. **Select and compare.** `mbedtls_ct_if` is a mask-and-or select. `mbedtls_ct_uint_lt` (`:271`) uses the sign bit of the difference, with a MSB-differs fix-up. `uint_ne` is XOR then `bool`. The rest are wrappers.
4. **Memory access.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and ORs every byte difference. Early exit is impossible. `mbedtls_ct_memcpy_if` always reads `len` bytes from both sources and selects with a mask.

Important limit: the contract is constant time with respect to the data, not the length. The header says so explicitly (`include/mbedtls/constant_time.h:19-20`).

## What happens on a compiler that cannot support it

The asm path is chosen by `constant_time_impl.h:40-52`. It requires all of:

- `MBEDTLS_HAVE_ASM` defined (`include/mbedtls/mbedtls_config.h:52`, which you can comment out),
- `__GNUC__`, which excludes MSVC and ARMCC 5,
- one of arm/thumb, aarch64, x86-64 or i386.

Otherwise `MBEDTLS_CT_ASM` is undefined and the code uses the C fallback. The fallback is silent. There is no `#warning` and no `#error`. The fallback's comment (`constant_time_internal.h`, `mbedtls_ct_bool`) says plain C was checked in May 2023 against trunk clang, gcc and MSVC, and was not turned into branches. That is a dated observation, not a guarantee. The fallback also depends entirely on the optimizer not seeing through `mbedtls_ct_zero`, and the comment itself calls it "fairly inefficient."

The only hard gate is `include/mbedtls/check_config.h:250`, which rejects MemorySanitizer combined with `MBEDTLS_HAVE_ASM`.

## How far it reaches

| Area | Evidence |
|---|---|
| Whole library | 444 `mbedtls_ct_*` or `constant_time` occurrences across 35 files in `library/` |
| Heaviest users | `rsa.c` (39), `bignum_core.c` (34), `cipher.c` (32), `ssl_msg.c` (26), `bignum.c` (27), `base64.c` (22), `psa_crypto.c` (11), `ssl_tls12_server.c` (10) |
| `mbedtls_ct_memcmp` callers | About two dozen, including the GCM/CCM/ChaCha20-Poly1305 tag checks, PKCS#1 v1.5 sign and verify, OAEP decrypt, TLS Finished and PSK binder checks, cookie check, and PSA MAC/hash verify |
| TLS record padding | `ssl_msg.c` `mbedtls_ct_hmac` (MAC-then-decrypt CBC) and the padding checks around lines 1916-1935 |
| RSA PMS | `ssl_parse_encrypted_pms` in `ssl_tls12_server.c` uses `mbedtls_ct_memcpy_if` |
| Bignum | `mbedtls_mpi_core_montmul` in `bignum_core.c` uses `mbedtls_ct_memcpy_if` |

Gaps and boundaries:

- **Public API.** Only `mbedtls_ct_memcmp` is public (`include/mbedtls/constant_time.h`). Everything else is internal.
- **`ecp.c` is not among the 35 files.** I did not read it. Constant-time EC behaviour therefore has to come through the bignum core, not the facility directly.
- **p256-m is separate.** `3rdparty/p256-m` has its own constant-time design, with its own `MUL64_IS_CONSTANT_TIME` switch, and does not call `mbedtls_ct_*`.
- **Outside the facility.** Cache-timing, variable-time division and branches in code that never calls the helpers are not covered by anything here.

## How it is verified

- **Valgrind.** `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (`mbedtls_config.h:2142`) runs under memcheck. Secrets are marked undefined, so a branch or address that depends on them is reported. The component keeps asm enabled, so it tests the asm path on the host.
- **MemorySanitizer.** `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` requires clang and `HAVE_ASM` unset (`tests/scripts/components-sanitizers.sh:33-51`). So it tests only the C fallback, not the asm.
- **Annotations.** Suites call `TEST_CF_SECRET(...)` (e.g. `tests/suites/test_suite_cipher.function:901`). I could not find that macro's definition in this checkout, so I cannot say what it expands to here.

Verification only covers inputs the tests drive through these paths. A clean run does not prove the property for other inputs or for compilers the CI does not build.