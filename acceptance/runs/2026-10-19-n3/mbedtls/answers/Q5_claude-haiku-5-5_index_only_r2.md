**Short answer:** Constant-time behaviour in mbedtls is a source-level discipline, backed by a small wrapper layer. The wrappers use inline assembly where the compiler allows it, and a `volatile` trick where it doesn't. Nothing in the build proves the emitted machine code is constant-time. The main dynamic check is a Valgrind test script. I could only see part of the code through the index, so the caveats below matter.

**1. How it is enforced at the instruction level**

- Secret-dependent values are wrapped in `mbedtls_ct_condition_t` (`library/constant_time_internal.h`). Comparisons and selects are written as bit operations (`mbedtls_ct_uint_lt`, `mbedtls_ct_bool_or/and/not`, `mbedtls_ct_uint_if`, and so on), not `if`s.
- `mbedtls_ct_compiler_opaque()` (`library/constant_time_impl.h:85`) is the optimizer barrier. With `MBEDTLS_CT_ASM` defined, it is an empty `asm volatile("" : [x] "+r"(x))`, so the compiler must treat `x` as unknown and cannot fold a branch back in. Its callers include `mbedtls_ct_bool`, `mbedtls_ct_if`, `mbedtls_ct_uint_lt/ne`, and `mbedtls_ct_memcpy_if`.
- `MBEDTLS_CT_TRUE` and `MBEDTLS_CT_FALSE` are built on that barrier (`SIZE_MAX`, `UINT64_MAX`, `UINT32_MAX` depending on width).
- `mbedtls_ct_uint_lt` has hand-written AArch64, Thumb/ARM and x86-64 assembly. Each computes the borrow-based comparison with `sub`/`sbc`-style sequences and sign-extends the result to a mask (`asr 63` / `asr #31` / `sar $63`), so no conditional jump is emitted.
- `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers, XORs them into an accumulator and never exits early, so the loop always touches every byte. Its doc comment states that it is constant-time with respect to the data but not with respect to `n`.

**2. What happens on a compiler that cannot support it**

`MBEDTLS_CT_ASM` is only defined when `MBEDTLS_HAVE_ASM` is set and the compiler is GCC/Clang-style (`__GNUC__`) or ARMCC (`library/constant_time_impl.h:40-52`). Otherwise:

- `mbedtls_ct_compiler_opaque(x)` returns `x ^ mbedtls_ct_zero`. `mbedtls_ct_zero` is a global `volatile` zero (`library/constant_time.c:29`), so the compiler cannot prove the value. This is a weaker barrier than an empty `asm volatile`, because the compiler still sees a real XOR and a real memory read.
- `mbedtls_ct_uint_lt` and the other comparisons fall back to portable C arithmetic when the architecture-specific assembly does not match. I did not read that fallback body; the index truncated it.

So on a non-GNU compiler, the code is still written branch-free at the source level, but the guarantee that the optimizer keeps it that way is weaker. The index does not record a compile-time error or warning for this case. The only `#error` I saw is the `int`-width check in `mbedtls_ct_memcmp`, which is unrelated.

**3. How far it reaches**

Callers the index resolves:

| Area | Constant-time users |
|---|---|
| `library/constant_time*.{c,h}` | Core helpers: `memcpy_if`, `memcpy_offset`, `memmove_left`, `zeroize_if`, `memcmp` |
| `library/bignum_core.c`, `bignum.c`, `bignum_internal.h` | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_gcd_modinv_odd`, `mbedtls_ct_mpi_sign_if` |
| `library/rsa.c` | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (Bleichenbacher-oracle hardening; the comment spells out the threat model), OAEP decrypt |
| `library/ssl_msg.c` | `mbedtls_ct_hmac`: constant-flow HMAC for CBC record MAC verification, using `psa_hash_clone` |
| `library/base64.c` | `mbedtls_ct_base64_enc_char` / `dec_value` |

Third-party code is separate: `3rdparty/everest` (HACL/Curve25519 extracted code) and `3rdparty/p256-m` have their own constant-time design. p256-m also has a `MUL64_IS_CONSTANT_TIME` config symbol for hardware where 32×32→64 multiply is constant-time.

**Verification:** `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh`) runs a dedicated set of constant-time tests under Valgrind. `docs/architecture/psa-shared-memory.md` notes that Valgrind memory poisoning is used for constant-flow testing, and MSan is mentioned as an alternative.

**Caveats I could not settle from the index**

- I did not verify whether the ECP, AES, or other crypto core code uses these wrappers. The name searches only surfaced the ones above. Coverage beyond them is unproven.
- `mbedtls_ct_memcmp` shows liveness `orphan`, with 26 callers unresolved. Treat its live-caller status as unknown rather than confirmed.
- The index has no config header recorded for this target, so I could not confirm which default configuration enables `MBEDTLS_CT_ASM` in a shipped build.
- Nothing I read proves the compiled output is branch-free. The opaque barrier reduces the risk; the Valgrind test is the check that exists.