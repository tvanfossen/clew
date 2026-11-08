**Short answer:** constant-time code in mbedtls is a small internal primitive layer, not a compiler guarantee. Assembly on four architectures pins the branch-free behaviour of the core operations. Everywhere else a plain-C fallback is used, with no build error and no warning. The layer is used in roughly 30 library files, and some sensitive paths deliberately bypass it.

**1. How it is enforced at the instruction level**

- The public surface is `include/mbedtls/constant_time.h`, which exports only `mbedtls_ct_memcmp()`. The real API lives in `library/constant_time_internal.h` and `library/constant_time_impl.h`.
- Secrets are represented as `mbedtls_ct_condition_t` values: all-ones for true, zero for false. Operations on them are bit masks, not comparisons. For example, `mbedtls_ct_bool(x)` turns any non-zero x into an all-ones mask using `neg`/`or`/`asr` (or the C equivalent).
- Selection is `mbedtls_ct_if(cond, a, b)` = `(cond & a) | (~cond & b)`. Comparisons such as `mbedtls_ct_uint_lt` are built from subtraction and sign-bit extraction.
- When asm is available, each primitive is hand-written `asm volatile` for AArch64, ARM/Thumb (32-bit), x86-64, and x86-32. The `volatile` keyword stops the compiler from removing or reordering the sequence, and the instruction choices avoid data-dependent branches or conditional moves.
- `mbedtls_ct_compiler_opaque(x)` hides a value from the optimiser. In asm it is an empty `asm volatile ("" : "+r"(x))`. In C it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero the compiler cannot fold away.
- Block operations (`mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset`, `mbedtls_ct_memcmp`, `mbedtls_ct_zeroize_if`, `mbedtls_ct_memmove_left`) read every byte or word on every path, with `volatile` pointers so the compiler cannot exit early.

**2. What happens on a compiler without support**

The asm branch is gated by `MBEDTLS_HAVE_ASM && __GNUC__` and excludes ARMCC5. Other compilers (MSVC, IAR, ARMCC5) and other architectures (RISC-V, MIPS, and so on) fall through to the `#else` C path. Nothing fails to compile and nothing warns.

The header's own comment says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023." That is an observation, not a guarantee. The C path relies on the optimiser not turning masks into branches. `MBEDTLS_HAVE_ASM` can also be disabled explicitly, which has the same effect. `check_config.h` forbids asm under MemorySanitizer, so that build also takes the C path.

**3. How it is tested**

- `tests/suites/test_suite_constant_time*.function` marks secrets with `TEST_CF_SECRET` and `TEST_CF_PUBLIC`.
- Two build options run those tests under detectors: `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (clang MemorySanitizer) and `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (memcheck). A secret-dependent branch or memory index shows up as use of uninitialised data.
- These checks catch secret-dependent control flow and addressing. They do not check cache or power side channels, which the ecp comb code addresses by reading the whole table.
- The sanitizer jobs live in `tests/scripts/components-sanitizers.sh`.

**4. How far it reaches**

| Area | Use of the layer | Examples |
|---|---|---|
| `bignum_core.c`, `bignum.c`, `bignum_mod_raw.c` | Heaviest user | `mbedtls_mpi_core_lt_ct`, conditional assign and swap, modular inverse |
| `rsa.c` | PKCS#1 v1.5 decryption and signature checks | `mbedtls_ct_rsaes_pkcs1_v15_unpadding`, `mbedtls_ct_memcmp` on encoded signatures, OAEP unpadding |
| `ssl_msg.c` | CBC record handling | Padding check, `mbedtls_ct_hmac` for MAC over the whole record, offset-dependent copy |
| `ssl_tls12_*`, `ssl_tls13_*`, `ssl_cookie.c` | Mostly `mbedtls_ct_memcmp` and selection | Finished-message and cookie comparisons |
| `cipher.c`, `psa_crypto_cipher.c` | CBC padding removal | `mbedtls_ct_uint_*` over the padding bytes |
| `ecp.c` | Scalar multiplication | `ecp_select_comb` reads the entire table and uses `MPI_ECP_COND_ASSIGN` |
| `base64.c`, `nist_kw.c`, `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `psa_crypto_mac.c` | Comparisons and decoding | Tag and value checks |

**Explicit gaps.** Several functions carry a "NOT constant-time" comment in `ecp.c`: `mbedtls_ecp_mul_shortcuts`, `mbedtls_ecp_muladd_restartable`, and `mbedtls_ecp_muladd`. The shortcut path is reached from the linear-combination (muladd) functions. I did not trace every caller to confirm that all of them handle public scalars only, so I cannot say the gap is harmless.

I found no constant-time claim in `aes.c`. It has no timing comments and I did not audit its table lookups, so I make no claim about AES.

Overall, the facility is applied to the places where the library processes secrets (RSA private operations, the TLS record MAC and padding path, ECC scalar multiplication, and tag comparisons). It is not a blanket property of the library. Its guarantee depends on the asm where it exists, and on an observed compiler behaviour where it does not.