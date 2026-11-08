## Short answer

Constant-time behaviour in mbedtls is a source-level discipline backed by two mechanisms: hand-written assembly for select architectures, and a C fallback that depends on the compiler not undoing it. Nothing in the build verifies the emitted instructions. The fallback degrades silently. The facility is internal and reaches only the code that opts into it, mostly bignum, PKCS#7 padding and MAC/tag comparison.

## How it is enforced at the instruction level

The primitives live in `library/constant_time_impl.h`, and every value is a mask rather than a boolean. `mbedtls_ct_condition_t` is all-ones (`MBEDTLS_CT_TRUE`) or zero (`MBEDTLS_CT_FALSE`). Branch-free selection and comparison are then bit operations on those masks.

- **Mask generation.** `mbedtls_ct_bool(x)` turns any non-zero `x` into an all-ones mask using `neg` / `or` / `asr`. There is an asm version per target, and the C version starts with `mbedtls_ct_compiler_opaque(x)`.
- **Selection.** `mbedtls_ct_if(cond, if1, if0)` is `and` / `not` / `and` / `or` on the mask, with asm variants for AArch64, ARM Thumb, x86-64 and x86-32.
- **Comparison.** `mbedtls_ct_uint_lt` uses the borrow trick: `sub`, `bic`, `orr`, then `asr` gives an all-ones or zero mask. `mbedtls_ct_uint_ne` is `diff = x ^ y` followed by `mbedtls_ct_bool(diff)`. `mbedtls_ct_uint_eq` is `~uint_ne`.
- **Compiler barrier.** `mbedtls_ct_compiler_opaque` is what stops the optimiser seeing through the mask. In the asm path it is `asm volatile("" : [x] "+r"(x))`. In the C path it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0 in `constant_time.c:29`. The compiler cannot prove the value is zero, so it cannot fold the mask back into a branch.
- **Buffers.** `mbedtls_ct_memcmp` (`constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the XOR differences, with no early exit. `mbedtls_ct_memcpy_offset` (`constant_time.c:214`) copies from every offset in `[offset_min, offset_max]` and selects with `mbedtls_ct_memcpy_if`, so the access pattern does not depend on the secret offset.

The asm paths are gated by `MBEDTLS_CT_ASM` (`constant_time_impl.h:42`). That needs `MBEDTLS_HAVE_ASM`, which is on in the shipped `mbedtls_config.h:52` and off in `configs/config-symmetric-only.h`, plus `__GNUC__` or `__ARMCC_VERSION`. Within that, each architecture macro (`MBEDTLS_CT_AARCH64_ASM`, `MBEDTLS_CT_ARM_ASM`, `MBEDTLS_CT_X86_64_ASM`, `MBEDTLS_CT_X86_ASM`) also requires a word-size macro (`MBEDTLS_CT_SIZE_32` or `_64`).

## What happens on a compiler that cannot support it

There is no build failure. Every primitive has a plain `#else` branch, so the library compiles everywhere. Selection is:

1. If `MBEDTLS_HAVE_ASM` is off, or the compiler is neither GCC-compatible nor ARMCC, or the architecture or word size has no asm variant, the C fallback is used.
2. The fallback is bit arithmetic plus `mbedtls_ct_compiler_opaque`. Its correctness rests on the compiler not turning those masks into branches or conditional moves.
3. The header says so in its own words. The `mbedtls_ct_bool` comment says the C fallback "does not get optimised into conditional instructions or branches" by the trunk clang, gcc and MSVC v19 of **May 2023**. That is a dated observation, not a guarantee.

The only compile-time guard in this area is in `mbedtls_ct_memcmp`. It `#error`s if `int` is narrower than 32 bits, because the final `(diff & 0xffff) | (diff >> 16)` cast would otherwise lose the sign-relevant bits. That protects the result's correctness, not its timing.

So on an unsupported toolchain the code still computes correct results, but the timing property is unverified and can break with no diagnostic. The library's own `SECURITY.md` caveat says "compilers can introduce timing side channels in code that was intended to be constant-time", and it disclaims guarantees against local non-timing side channels.

The only dynamic check the index shows is `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`). It runs the `tests/suites/*constant_time*.data` suites under Valgrind, excluding the HMAC data file. The index does not show how Valgrind is made to detect secret-dependent behaviour, so I cannot say more about the mechanism.

## How far it reaches

- **Public surface: none.** `docs/psa-transition.md` lists `constant_time.h` as an "internal support header" with no public APIs. Its `mbedtls_ct_` names are library-internal.
- **Bignum.** `mbedtls_mpi_core_lt_ct` (`bignum_core.c:133`) scans all limbs with no early exit. `mbedtls_mpi_core_check_zero_ct`, and the public `mbedtls_mpi_lt_mpi_ct` in `bignum.h`, are also documented as constant-time. The first is documented as constant-time with respect to the value but not the limb count.
- **PKCS#7 padding.** `mbedtls_get_pkcs_padding` (`cipher.c:847`) runs a fixed `input_len` loop. Its comment says the number of bytes checked "must be independent of padding_len". It accumulates `bad` through `mbedtls_ct_bool_or` and returns the length through `mbedtls_ct_if`, so the error is not revealed by timing. This is the clearest real consumer.
- **Documented intent elsewhere.** The PSA headers ask implementations to "make the best effort" for constant-time tag and MAC comparison in `psa_mac_verify_finish`, `psa_hash_verify`, `psa_aead_verify` and `psa_key_derivation_verify_bytes`. That is a best-effort obligation, not a verified one.
- **Length leaks by design.** `mbedtls_ct_memcmp` is explicitly "not constant-time w.r.t. n", and `mbedtls_ct_memcpy_offset` depends on `offset_min`, `offset_max` and `len`. Lengths are public inputs for these callers.
- **Separate story in third-party code.** `3rdparty/p256-m` has its own constant-time design. It uses Fermat inversion and a `MUL64_IS_CONSTANT_TIME` symbol for platforms with a constant-time 32×32→64 multiply. It does not use `mbedtls_ct_*`.

The index cannot enumerate the full consumer set. It reports 26 unresolved call sites for `mbedtls_ct_memcmp`, 12 for `mbedtls_ct_uint_eq` and 25 for `mbedtls_ct_bool`. So the list above is a sample of resolved callers, not a census. To count every caller, grep `mbedtls_ct_` across `library/` directly.