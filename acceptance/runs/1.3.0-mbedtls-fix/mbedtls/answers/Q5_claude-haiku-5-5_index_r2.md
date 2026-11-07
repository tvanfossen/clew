**Short answer:** The facility is a small set of branch-free primitives in `library/constant_time_impl.h`. Inline asm produces the all-ones/all-zeros mask on the four architectures it covers. Everywhere else it falls back to plain C that is only observed to be constant-time, and nothing fails to build. The primitives reach the RSA, record-layer, cipher-padding, tag-compare and bignum code. ECC point arithmetic in `ecp.c` does not use them, and parts of it are documented as not constant-time.

**How it is enforced at the instruction level**

- **Mask generation is the enforced part.** `mbedtls_ct_bool(x)` turns any value into all-ones (true) or zero (false). On x86-64 it is `mov x→s; neg s; or x,s; sar $63,s`, so there is no branch or conditional instruction. AArch64, ARM/Thumb and x86 have equivalent sequences (`constant_time_impl.h:120–203`).
- **The asm stops the compiler from rewriting the mask.** `MBEDTLS_CT_ASM` is defined when `MBEDTLS_HAVE_ASM` is set and the compiler is GNU-compatible (`constant_time_impl.h:40–52`). `mbedtls_ct_compiler_opaque` is then an `asm volatile("" : "+r"(x))` barrier, so the compiler cannot prove a condition's value and fold it.
- **Everything else is built from the mask.** Comparisons, `mbedtls_ct_if`, `mbedtls_ct_memcpy_if` and `mbedtls_ct_zeroize_if` use bit operations. Table lookups read every entry: `mbedtls_mpi_core_ct_uint_table_lookup` (`bignum_core.c:597`) scans the whole table and selects with `uint_eq`. `mbedtls_ct_memcmp` (`constant_time.c:67`) reads through `volatile` pointers, never exits early, and ORs the differences together.
- **The condition type is opaque.** `MBEDTLS_CT_TRUE`/`FALSE` are wrapped in `compiler_opaque`, and the header says callers must not manipulate the value directly (`constant_time_internal.h:40–47`).

**What happens on a compiler that cannot support it**

The fallback is chosen when any of these holds:

- `MBEDTLS_HAVE_ASM` is off.
- The compiler is not GNU-compatible (MSVC, or armcc5 before 6.0).
- The architecture is not one of the four with asm (RISC-V and MIPS, for example). Even with GCC, `mbedtls_ct_bool` then uses C while `compiler_opaque` still uses the asm barrier.

In the fallback, `compiler_opaque` is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global holding 0. `mbedtls_ct_bool` uses the arithmetic sign-bit trick `(-x) | -(x>>1)`. The header says this "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55–59`). That is an observation about compiler output, not a guarantee. The build succeeds without warning and nothing checks the emitted code.

**How it is tested**

- **Valgrind constant-flow:** `components-sanitizers.sh:105–152` marks secrets as undefined, so a secret-dependent branch or address is reported as use of uninitialised memory. There is one run without asm and one with asm.
- **MemorySanitizer:** the MSan component turns asm off. `check_config.h:250` rejects MSan with `MBEDTLS_HAVE_ASM`. So MSan only exercises the C fallback.
- These are dynamic checks on the inputs the tests happen to use, on the CI host's architecture. They are not proof for other hardware or compilers.

**How far it reaches**

- **Public API:** only `mbedtls_ct_memcmp` is in `include/mbedtls/constant_time.h`. Everything else is internal. Its doc says it is not constant-time with respect to `n`, so buffer length can leak.
- **Users:** about 465 occurrences across 30 library files, from the counts I took. Main groups:
  - **Record layer:** `ssl_msg.c` (`mbedtls_ssl_decrypt_buf`, `mbedtls_ct_hmac`, padding checks), plus TLS 1.2/1.3 Finished and PSK binder comparisons.
  - **RSA:** PKCS#1 v1.5 unpadding, OAEP decrypt, and signature-verify comparisons.
  - **Cipher padding:** `cipher.c` (`get_pkcs_padding`, `get_zeros_and_len_padding`).
  - **Tag comparisons:** GCM, CCM, ChaCha20-Poly1305, NIST KW, PSA MAC and hash verify.
  - **Bignum:** `bignum_core.c` (table lookup, conditional assign and swap, `lt_ct`, `check_zero_ct`), `bignum_mod_raw.c`, and the GCD/modinv path in `bignum.c`.
- **Gaps:**
  - `ecp.c` calls no `mbedtls_ct_*` functions. Its comments mark `mbedtls_ecp_mul_shortcuts` (the m = 0, 1, −1 shortcuts) and `mbedtls_ecp_muladd` as NOT constant-time. The comb method is commented as constant-time, but I did not trace whether the variable-base path is constant-time end to end.
  - `exp_mod` in `bignum_core.c:756–760` and `:806` is not constant-time with respect to the exponent when the exponent is marked public, or with respect to the window parameter.
  - The third-party p256-m has its own constant-time discipline (`MUL64_IS_CONSTANT_TIME`) and does not use this facility.

**Not verified:** how `TEST_CF_SECRET` is implemented (I read only the component comments), the base64 call sites (the grep counted 21 hits but I did not read them), and DHM.