## Short answer

Mbed TLS does not enforce constant time with a compiler flag or a verifier. It uses a set of branch-free primitives built on a "hide the value from the compiler" trick, plus per-architecture inline assembly where the C fallback is not trusted. The library admits that the compiler can still break this, and nothing in the index shows a build-time check that the result is constant time.

## How it works at the instruction level

The core primitive is `mbedtls_ct_compiler_opaque()` in `library/constant_time_impl.h:85`. It returns its argument unchanged, but the compiler is told not to know the value:

- **With `MBEDTLS_CT_ASM`:** `asm volatile("" : [x] "+r" (x) :)`, an empty asm that forces the value into a register and makes it opaque.
- **Without it:** `return x ^ mbedtls_ct_zero;`, where `mbedtls_ct_zero` is a `volatile` global (`library/constant_time.c:29`) set to 0. The compiler cannot fold the XOR away.

Conditions are kept as full-width masks, `mbedtls_ct_condition_t`, where `MBEDTLS_CT_TRUE` is all ones and `MBEDTLS_CT_FALSE` is zero (`library/constant_time_internal.h:70`). Every operation on secrets is then bit arithmetic. `mbedtls_ct_bool()` (`constant_time_impl.h:120`) turns a value into a mask. It has a hand-written asm version per target:

| Target | Asm path |
|---|---|
| AArch64 | `neg` / `orr` / `asr` |
| 32-bit ARM (Thumb) | `negs` / `orrs` / `asrs` |
| x86-64 | `mov` / `neg` / `or` / `sar` |
| 32-bit x86 | the same sequence on 32-bit registers |

Its plain-C fallback uses `(-xo) | -(xo >> 1)` and a sign-bit extraction. The source comment says that as of May 2023 trunk clang, gcc and MSVC do not turn it into branches. That is an observation about specific compiler versions, not a guarantee.

Higher-level operations are built from these, for example:

- `mbedtls_ct_memcmp()` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers, XORs them into an accumulator, and returns a value that is zero only when the buffers match. It is constant-time with respect to the data but not with respect to `n`.
- `mbedtls_ct_memcpy_if()` (`constant_time.c:169`) does a masked copy that always reads both sources.

## What happens on a compiler that cannot support it

Nothing fails at build time. The asm paths are gated on `MBEDTLS_HAVE_ASM` and on `__GNUC__` or `__ARMCC_VERSION` (`constant_time_impl.h:40-52`, which defines `MBEDTLS_CT_ASM`). On a compiler that does not match, such as MSVC or IAR, `MBEDTLS_CT_ASM` is not defined, and the code falls back to:

- the `volatile` XOR trick for `compiler_opaque`, and
- the plain-C arithmetic in `mbedtls_ct_bool`.

The fallback is weaker. Nothing forces the compiler to keep the arithmetic branch-free. `SECURITY.md` ("Caveats") says that compilers can introduce timing side channels in code meant to be constant time, and that the project treats exploitable ones as vulnerabilities when they appear with a common compiler. The fallback is therefore best-effort, and the index holds no evidence that it is verified on every toolchain.

## How far it reaches

The facility is used in a limited set of places:

- **Public API:** `mbedtls_ct_memcmp()` in `include/mbedtls/constant_time.h`. Its `mbedtls_ct_*` family is documented in `docs/psa-transition.md`.
- **Bignum:** `mbedtls_mpi_core_lt_ct()` (`library/bignum_core.c:133`), `mbedtls_mpi_core_check_zero_ct()`, `mbedtls_mpi_lt_mpi_ct()`, and the `mbedtls_mpi_gcd_modinv_odd` wrapper.
- **RSA:** `mbedtls_ct_rsaes_pkcs1_v15_unpadding()` (`library/rsa.c:420`) processes the whole padded block, with the padding check kept in masks to guard against Bleichenbacher-style oracles. OAEP decryption also uses the masks.
- **TLS record layer:** `mbedtls_ssl_decrypt_buf()` (`library/ssl_msg.c:1482`) uses `MBEDTLS_CT_TRUE` and a masked padding check for CBC. `mbedtls_ct_hmac()` (`ssl_msg.c:65`) computes the MAC over a fixed amount of data, cloning the hash context so the work does not depend on the true length.
- **Base64:** `mbedtls_ct_base64_dec_value()` (`library/base64.c:40`) decodes without table lookups that depend on the input.

Outside this set, the index does not show the facility in use. It also does not show any coverage of AES, ECP or the PSA layer. `docs/psa-transition.md` says PSA has no equivalent of these utilities, and the PSA `psa_aead_verify` documentation asks implementations to make the tag comparison constant-time on a best-effort basis. Separately, `3rdparty/p256-m` is described as constant-time throughout, with its own `MUL64_IS_CONSTANT_TIME` switch.

Testing is partial. `tests/scripts/components-configuration-crypto.sh` has `test_with_valgrind_constant_time`, which runs a small set of dedicated constant-time suites under Valgrind and excludes slow suites. The index also lists `CT_VALGRIND` and `CT_MEMSAN` as gate symbols. I did not confirm the test suites themselves.

`SECURITY.md` ("Local attacks") says Mbed TLS makes no security guarantees against local non-timing side channels. Remote timing of packets is a separate matter that it also does not address.

## Limits of this answer

- The index does not show which asm path is active in the shipped default build. The only configured macros recorded are `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD`, and no config header is recorded for this target. So I cannot say which `MBEDTLS_CT_*` path a default build takes.
- Liveness for `mbedtls_ct_memcmp` is reported as `orphan`, while `callers_unresolved` is 26. That is probably a resolution gap, not evidence that nothing calls it, but I could not settle it from the index.
- I have not read the generated machine code, so whether the compiler keeps these sequences branch-free is not something the index can show.