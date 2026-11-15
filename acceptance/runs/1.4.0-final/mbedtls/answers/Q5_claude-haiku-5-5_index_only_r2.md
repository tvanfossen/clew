## Short answer

Constant time in mbedtls is a **convention enforced by code shape and a few compiler barriers**, not by a compiler or build check. The strongest guarantee comes from hand-written inline assembly, which exists only on a few architectures. Everywhere else, the code falls back to plain C that the authors believe, but cannot guarantee, a compiler will leave branch-free. Coverage is opt-in per function.

## How it is enforced at the instruction level

The facility is `library/constant_time_impl.h`, with `constant_time.c` and `constant_time_internal.h` alongside it. It works in three layers:

1. **Branch-free masking.** Secrets are turned into a mask rather than tested. `mbedtls_ct_bool(x)` produces an all-ones or all-zeros `mbedtls_ct_condition_t` from `x != 0`. `mbedtls_ct_if`, `mbedtls_ct_bool_and/or/not`, and `mbedtls_ct_uint_lt/eq/ne` combine masks with AND/OR/NOT, so no secret reaches a branch.

2. **Optimizer barriers.** `mbedtls_ct_compiler_opaque(x)` (`constant_time_impl.h:85`) hides a value from the compiler so it cannot prove the mask is constant. With `MBEDTLS_CT_ASM` it is an empty `asm volatile("" : [x] "+r" (x))`. Without it, it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`constant_time.c:29`).

3. **Hand-written asm for the critical primitives.** `mbedtls_ct_bool` and `mbedtls_ct_if` have asm bodies for AArch64, 32-bit ARM (Thumb-2 `l` registers), x86_64, and 32-bit x86. The asm pins the instruction sequence, for example `neg / or / sar 63` for the bool mask. Each arch branch is further gated by a size macro, `MBEDTLS_CT_SIZE_32` or `MBEDTLS_CT_SIZE_64`.

## What happens on a compiler that cannot support it

The asm is gated by `MBEDTLS_CT_ASM`, which is defined only when `MBEDTLS_HAVE_ASM` is on (on by default, `mbedtls_config.h:52`) **and** the compiler is GCC-like (`__GNUC__`) or ARMCC (`__ARMCC_VERSION`). Otherwise:

- The `#if` chain drops to the C fallback in each primitive.
- The optimizer barrier degrades from an asm barrier to a `volatile` load. That is a weaker guarantee: it blocks constant folding but places no constraint on how the compiler generates the surrounding branches.
- The code comment says the C fallback "in May 2023 does not get optimised into conditional instructions or branches" by trunk clang, gcc, or MSVC. That is a dated observation about specific compiler versions, not a guarantee.

I found no `#error` or refusal path in the index. An unsupported compiler gets the C fallback silently, so the guarantee quietly weakens. `SECURITY.md` says compilers can introduce timing channels in code meant to be constant time.

## How far it reaches

The primitives are used in security-sensitive spots:

| Area | Users of the primitives |
|---|---|
| RSA | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (explicitly written against Bleichenbacher-style padding oracles), `mbedtls_rsa_rsaes_oaep_decrypt` |
| TLS server | `ssl_parse_encrypted_pms` (RSA pre-master-secret handling), `mbedtls_ct_hmac` in `ssl_msg.c` (CBC MAC verification) |
| Padding removal | `cipher.c` padding helpers (`get_pkcs_padding`, `get_one_and_zeros_padding`, `get_zeros_and_len_padding`), `psa_crypto.c` cipher decrypt/finish |
| Bignum | `bignum_core.c` (`mbedtls_mpi_core_montmul`, `lt_ct`, `gcd_modinv_odd`, `add_if`, `check_zero_ct`), `bignum.c` (`safe_cond_assign/swap`, `lt_mpi_ct`), `bignum_mod_raw.c` cond assign/swap |
| Other | `cmac.c`, `nist_kw.c` unwrap, `constant_time` memcpy/memmove/zeroize helpers |

Two things are outside this umbrella:

- **Code that does not call these primitives** is not covered. The facility is opt-in per function, and the index shows no global guarantee.
- **`3rdparty/p256-m`** is a separate library with its own constant-time macros (`CT_POISON` / `CT_UNPOISON`, `MUL64_IS_CONSTANT_TIME`, `CT_VALGRIND`, `CT_MEMSAN`) and its own design, not the `mbedtls_ct_*` layer.

## How it is tested

The index shows Valgrind and MemorySanitizer constant-flow components (`component_release_test_valgrind_constant_flow`, `..._no_asm`, `..._psa`, `test_with_valgrind_constant_time`, `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`). The `_no_asm` variant means the C fallback path is tested as well as the asm one. Those checks run on exercised paths only, so they show the absence of secret-dependent branches and memory access where tested, not across the whole library. I did not read the test-harness poisoning helpers in the index, so I cannot say exactly how secrets are marked in mbedtls's own test suites.