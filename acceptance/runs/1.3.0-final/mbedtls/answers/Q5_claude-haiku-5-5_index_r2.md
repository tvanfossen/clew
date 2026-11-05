**Short answer:** Constant-time behaviour is a convention backed by hand-written assembly on four architecture families, with a plain-C fallback that is silently weaker. Nothing in the build checks the emitted code. The facility covers the bignum, RSA-padding, cipher-padding, MAC-comparison and TLS record paths. ECC scalar multiplication, the one place it matters most, does not use it.

**1. How it is enforced at the instruction level**

The primitives live in `library/constant_time_impl.h`, with the typedefs in `constant_time_internal.h`. Every secret-dependent choice is expressed as arithmetic on an all-ones or all-zeros mask, so there is no branch to take:

- `mbedtls_ct_bool(x)` turns any nonzero value into an all-ones mask. On x86-64 it is `mov`/`neg`/`or`/`sar $63`, with no flag-dependent instruction.
- `mbedtls_ct_if(c, a, b)` is `and`/`not`/`and`/`or`, a bitwise select.
- `mbedtls_ct_uint_lt` uses the borrow/sign-bit formula, again with no `cmp` plus `jcc`.

Two things stop the compiler from undoing this:

- Each asm block is `asm volatile`, so the compiler cannot remove or reorder it.
- `mbedtls_ct_compiler_opaque(x)` launders a value through an empty asm barrier (asm path) or XORs it with a `volatile` global zero (C path). That keeps the compiler from constant-folding a condition it could otherwise prove.

Memory access is handled the same way. `mbedtls_ct_memcmp` reads every byte through `volatile` pointers and never exits early. `mbedtls_ct_memcpy_if` always reads both sources and blends them with masks. `mbedtls_ct_memcpy_offset` walks every possible offset and selects the real one.

Assembly is selected in `constant_time_impl.h:40-52`. It needs `MBEDTLS_HAVE_ASM`, `__GNUC__` (clang included), and not armcc5. It then picks one of four families:

| Family | Macro | Widths covered |
|---|---|---|
| ARM / Thumb | `MBEDTLS_CT_ARM_ASM` | 32-bit |
| AArch64 | `MBEDTLS_CT_AARCH64_ASM` | 32 and 64-bit |
| x86-64 | `MBEDTLS_CT_X86_64_ASM` | 32 and 64-bit |
| x86 | `MBEDTLS_CT_X86_ASM` | 32-bit |

Each primitive also checks the word width, so an ARM build with 64-bit `mbedtls_ct_uint_t` drops to C for that primitive.

**2. What happens on a compiler that cannot support it**

Nothing fails. There is no `#error`. The code falls through to C fallbacks:

- Non-GNU compilers (MSVC), armcc5, and architectures without a matching asm block all take the C path.
- `MBEDTLS_HAVE_ASM` is defined by default (`mbedtls_config.h:52`), so it is the platform gate, not the compiler gate. Disabling it, or building on an unsupported arch, silently switches the whole layer to C.
- The C fallback is plain arithmetic. Its header comment says it "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation, not a guarantee, and the compiler can change under it.
- `SECURITY.md:107-111` says so directly: compilers can introduce timing side channels, "this prevention may not be complete", and only common levels such as `-O2`/`-Os` are scrutinised. Higher levels are "less scrutinized".

The sanitizer CI components unset `MBEDTLS_HAVE_ASM` for several configurations (`tests/scripts/components-sanitizers.sh:45,120,175`). `check_config.h:250` has a guard tied to `MBEDTLS_HAS_MEMSAN` and `MBEDTLS_HAVE_ASM`. I did not read the body of that guard.

**3. How it is checked**

Nothing verifies the compiled output. The checks are dynamic and opt-in:

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (`mbedtls_config.h:2109-2142`) make selected tests also check the constant-flow property. Per the header comments, this uses valgrind memcheck or clang MemorySanitizer.
- `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs `tests/suites/*constant_time*.data`.
- Only the paths those suites exercise are covered, and only for the configurations CI runs.

`SECURITY.md:57-65` says the protection is "limited", aims only at "publicly documented attack techniques", and that the project "has not reached" fully timing-invariant code.

**4. How far it reaches**

Calls to `mbedtls_ct_*` appear in 29 library files. The 286-occurrence count includes the header definitions, so the real call-site count is lower. The main users:

- **Bignum:** `bignum.c`, `bignum_core.c`, `bignum_mod_raw.c` (`mbedtls_mpi_core_lt_ct`, `check_zero_ct`, `montmul`, `gcd_modinv_odd`).
- **RSA:** `rsa.c` (`mbedtls_ct_rsaes_pkcs1_v15_unpadding`).
- **Symmetric padding and MAC:** `cipher.c` (CBC padding removal, the largest user at about 25 references), `cmac.c`, `ccm.c`, `gcm.c`, `chachapoly.c`, `nist_kw.c` (`mbedtls_ct_memcmp_partial`).
- **TLS:** `ssl_msg.c` (record MAC and padding), `ssl_tls12_*`, `ssl_tls13_*`, `ssl_cookie.c`.
- **PSA:** `psa_crypto*.c` and the driver wrappers.
- **Encoding:** `base64.c`.

Gaps:

- **ECC (`ecp.c`, `ecdsa.c`, `ecdh.c`):** none of these call the `mbedtls_ct_*` layer. `ecp.c` uses its own scheme: a recoded scalar, fixed operation counts, and reads of the whole precomputed table (`ecp_select_comb`, lines ~2010-2020, "to thwart cache-based timing attacks"). Several helpers are explicitly labelled "NOT constant-time" (lines 2734, 2769, 2873). I did not audit that scheme.
- **AES (`aes.c`):** no `mbedtls_ct_*` references. Any protection there does not come from this layer, and I did not audit the table implementation.
- **`3rdparty/p256-m`:** a separate, fully constant-time P-256 implementation with its own `MUL64_IS_CONSTANT_TIME` switch. It is outside this facility.

**Bottom line:** the facility gives strong, asm-enforced data-independence for the primitives that use it, on four architecture families. Everywhere else, and on any compiler or platform that falls back to C, the guarantee is weaker, and the project says so in `SECURITY.md`.