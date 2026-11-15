## Short answer

Constant time in mbedtls is enforced by hand-written inline assembly on four architectures, with a portable C fallback everywhere else. The fallback has no compile-time check and no warning. It depends on the compiler not turning code into branches, which the code itself describes as "observed" rather than guaranteed. The facility is also applied unevenly: it covers padding, tag, and signature checks and the bignum core, but not the block ciphers and only partly ECP.

## How it is enforced at the instruction level

All secret-dependent decisions are written as bitmasks, not `if` statements. `mbedtls_ct_condition_t` is an all-ones or all-zeros word, and selection is done with AND/OR. The core primitive is `mbedtls_ct_bool(x)`, which turns "x != 0" into a mask. On x86-64 (`library/constant_time_impl.h:157`) it is:

```
mov  x -> s
neg  s            ; s = -x
or   x, s         ; sign bit set iff x != 0
sar  $63, s       ; s = all ones iff x != 0
```

Every other operation is built on that mask. For example, `mbedtls_ct_if(c, a, b)` is `(c & a) | (~c & b)`, and comparisons such as `mbedtls_ct_uint_lt` are built from subtraction and sign extraction.

Two mechanisms keep the optimiser from undoing this:

- **Opaque barrier.** `mbedtls_ct_compiler_opaque(x)` is `asm volatile("" : "+r"(x))` when asm is available. Otherwise it XORs with `mbedtls_ct_zero`, a `volatile` global (`library/constant_time.c:29`). The compiler therefore cannot prove a secret's value, so it cannot fold a mask into a branch.
- **Volatile reads for memory.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the differences. It always reads every byte, so it cannot exit early on the first mismatch. Its only C-level guarantee is the `volatile` access; no assembly is involved.

## What happens on a compiler or target that cannot support it

The gate is in `library/constant_time_impl.h:40-52`:

| Condition | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` and GCC or Clang (or armcc ≥ 6) | `MBEDTLS_CT_ASM` defined |
| …and target is ARM, AArch64, x86-64, or i386 | matching `MBEDTLS_CT_*_ASM` defined; asm used for bool/if/lt |
| …and target is anything else (e.g. RISC-V) | barrier is the empty asm, but bool/if/lt use the **C fallback**; `mbedtls_ct_zero` is not defined |
| MSVC, or `MBEDTLS_HAVE_ASM` not defined | no asm; barrier is `x ^ mbedtls_ct_zero`, C fallback everywhere |

Nothing fails. There is no `#error`, no warning and no configuration check for a missing asm path. The only `#error` near this code is the 32-bit-int guard in `constant_time.c:105`. The header says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). That is an observation, not a guarantee.

`SECURITY.md:57-65` is more candid: protection is "limited", aims only at "publicly documented attack techniques", and "has not reached" fully timing-invariant code. Line 109 says compiler options and target platforms may make the protection incomplete.

## Testing the property

Two opt-in mechanisms exist, both documented in `mbedtls_config.h:2108-2142`:

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`: runs the constant-time suites under Valgrind memcheck, which flags secret-dependent branches on uninitialised data. The CI component `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh:25-33` does this.
- `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`: the same idea with Clang MemorySanitizer. `check_config.h:248` refuses the setting unless built with MemorySanitizer.

Neither runs by default in a normal build. Both test the compiled output, not the source, so they catch what the compiler actually produced on the tested platform.

## How far it reaches

`mbedtls_ct_*` and the `MBEDTLS_CT_TRUE`/`FALSE` constants appear about 456 times across 29 library files. The heaviest users, by count:

| File | Occurrences | Role |
|---|---|---|
| `rsa.c` | 40 | PKCS#1 v1.5 and OAEP unpadding, signature comparison |
| `bignum_core.c` | 32 | Constant-time compare, zero check, modular inversion helpers |
| `cipher.c` | 30 | CBC padding removal, tag comparison |
| `bignum.c` | 29 | Public MPI wrappers over the core |
| `ssl_msg.c` | 27 | Record padding and MAC checks |
| `base64.c` | 21 | Decoding without data-dependent branches |
| `ssl_tls12_server.c` | 9, `psa_crypto.c` 9 | Handshake and PSA paths |

Other files use it lightly, including `chachapoly.c` and `ssl_tls.c`, which compare tags or handshake data with `mbedtls_ct_memcmp`.

The gaps:

- **`ecp.c` does not use the `mbedtls_ct_*` primitives.** It has its own constant-time comb recoding and parity fix (around lines 2108-2140), and several functions are explicitly marked "NOT constant-time" (lines 2734, 2769, 2873).
- **`aes.c` uses none of it.** `SECURITY.md:72-73` says block ciphers do not yet achieve full protection.
- **`3rdparty/p256-m` has its own gating.** It uses a separate `MUL64_IS_CONSTANT_TIME` symbol, outside the `mbedtls_ct_*` facility.
- **Public API.** Only `mbedtls_ct_memcmp` is public (`include/mbedtls/constant_time.h`). The rest is internal, so applications cannot rely on the masks directly.

I did not check `gcm.c`, `ccm.c` or `cmac.c` beyond a single match each, so I cannot say how their tag comparisons are done.