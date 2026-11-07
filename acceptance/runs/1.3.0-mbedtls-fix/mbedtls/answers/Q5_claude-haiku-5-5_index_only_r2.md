## Short answer

Constant-time behaviour is enforced by hand-written inline assembly for a few primitives, with a volatile-based C fallback everywhere else. The facility is a small set of helpers in `library/constant_time_impl.h`, and it is used by roughly 40 call sites across bignum, cipher padding, MAC/AEAD tag checks, RSA, PSA and TLS. Nothing in the index shows a compile-time error for unsupported compilers; the fallback is silent.

## How it works at the instruction level

The core is a set of branch-free primitives. Each returns an `mbedtls_ct_condition_t` (all-ones or zero) and the caller selects with masks:

- `mbedtls_ct_uint_lt` computes the sign bit of `x - y` using the standard borrow trick: `((x ^ ((x ^ y) | ((x - y) ^ y))) >> top)`-style bit logic. The index shows it as `eor / sub / bic / and / orr / asr` on AArch64, `eors / subs / bics / ands / orrs / asrs` on Thumb/ARM, and `mov / xor / sub / and / not / and / or / sar` on x86-64.
- `mbedtls_ct_if` selects with `and / not / and / or` (or the AArch64/ARM equivalents) instead of a `?:`.
- `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the XOR of every byte into `diff`. The comment says the volatile cast forces both buffers to be fully read, so the compiler cannot add an early exit. The return value is `(diff & 0xffff) | (diff >> 16)`, which is non-zero iff `diff` is non-zero. Its docs say it is constant-time with respect to the data but **not** with respect to `n`.

Two things stop the optimizer from undoing this:

- `mbedtls_ct_compiler_opaque` (`constant_time_impl.h:85`) passes a value through an empty `asm volatile` with a `+r` constraint, so the compiler cannot prove what the value is. This is what makes `x = opaque(1)` unknown to the compiler.
- `mbedtls_ct_zero` is a `volatile` global set to 0 (`constant_time.c:29`). It is used as the fallback "opaque" operand.

## What happens on a compiler without the asm path

The asm path is selected by `MBEDTLS_CT_ASM` (`constant_time_impl.h:42`), which is gated on `MBEDTLS_HAVE_ASM` and on `__GNUC__` or `__ARMCC_VERSION`. Within that, the architecture macros `MBEDTLS_CT_AARCH64_ASM`, `MBEDTLS_CT_ARM_ASM`, `MBEDTLS_CT_X86_64_ASM` and `MBEDTLS_CT_X86_ASM` pick a variant, and `MBEDTLS_CT_SIZE_32` / `MBEDTLS_CT_SIZE_64` pick the word size.

If none of these match, the code falls through to portable C:

- `mbedtls_ct_compiler_opaque` returns `x ^ mbedtls_ct_zero`. The `volatile` load is a barrier the compiler must honour, but it is much weaker than an asm barrier.
- `mbedtls_ct_if` uses `(condition & if1) | (~opaque(condition) & if0)`.

So an unsupported compiler does not fail the build. It gets the C fallback, and the guarantee rests on the optimizer not reasoning through `volatile` and the `~opaque` trick. `SECURITY.md` says the project "use[s] standard C except with known compilers" and that compilers "can introduce timing side channels in code that was intended to be constant-time." I could only see a snippet of that file in search; the file-level dossier returned no body, so I cannot quote the full caveat.

## How far it reaches

Callers found in the index (names from the call graph):

| Area | Uses |
|---|---|
| Bignum | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_core_uint_le_mpi`, `mbedtls_mpi_core_cond_assign` / `cond_swap` / `add_if`, `mbedtls_mpi_core_ct_uint_table_lookup`, `mbedtls_mpi_mod_raw_cond_*`, `mbedtls_mpi_safe_cond_*` |
| Cipher padding | `get_zeros_padding`, `get_one_and_zeros_padding`, `get_zeros_and_len_padding`, `mbedtls_get_pkcs_padding`, `mbedtls_cipher_finish` |
| Tag verification | `mbedtls_ct_memcmp` is called from CCM, ChaCha20-Poly1305, GCM, `mbedtls_cipher_check_tag`, NIST KW unwrap, PSA MAC/hash verify and compare |
| RSA | PKCS#1 v1.5 sign/verify/decrypt, OAEP decrypt |
| TLS | renegotiation info, PSK identity and binder checks, TLS 1.3 Finished, cookie check, `mbedtls_ssl_decrypt_buf` |
| Other | base64 encode/decode (`mbedtls_ct_base64_*`), `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset`, `mbedtls_ct_zeroize_if`, `mbedtls_ct_memmove_left` |

The facility is not used everywhere. `3rdparty/p256-m` has its own constant-time story, gated by `MUL64_IS_CONSTANT_TIME`, and I did not look at it further. The PSA docs say the PSA API has no equivalent to the `constant_time.h` utilities, so PSA callers reach the same helpers only through the internal implementation.

## How it is tested

- `test_suite_constant_time` is a dedicated suite.
- `component_release_test_valgrind_constant_flow` (`tests/scripts/components-sanitizers.sh:72`) builds with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`. Secret inputs are marked as uninitialised, so Memcheck reports any branch or memory access that depends on them. It runs the full suite set, then runs the constant-time suite again on the asm path.
- `test_with_valgrind_constant_time` runs only the `*constant_time*.data` suites under Valgrind.

The test script notes that by default the constant-time suite exercises the plain C path under Valgrind or MemSanitizer. The asm path is only checked when it is built in.

## Gaps in what I could establish

- I could not see whether `MBEDTLS_HAVE_ASM` is on in the default config. The gate reports its default site as `mbedtls_config.h:52`, but I did not read it.
- The index does not show whether any build or CI step checks that the asm path was actually selected. If nothing does, a build on an unsupported compiler silently gets the weaker C fallback.