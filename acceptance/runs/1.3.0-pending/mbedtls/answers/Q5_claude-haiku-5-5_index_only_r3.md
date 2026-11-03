## Short answer

Constant-time behaviour in mbedtls is a set of branchless primitives in `library/constant_time*.{c,h}`, not a whole-library guarantee. The main enforcement is inline assembly where available plus a `volatile` trick elsewhere. Nothing fails the build on an unsupported compiler; the portable C fallback is used silently. The facility's reach into the rest of the library is narrower than the name suggests. Bignum and a few other spots use it, and a lot of the library does not, as far as this index shows.

## How it is enforced at the instruction level

Everything is built from a few primitives, all operating on a `mbedtls_ct_condition_t` that is either all-zeros or all-ones:

- **`mbedtls_ct_bool(x)`** turns a value into a mask: nonzero becomes all-ones, zero stays zero. The x86-64 version is three instructions (`mov`, `neg`, `or`, `sar $63`). The AArch64, 32-bit ARM and 32-bit x86 variants are similar, all in `asm volatile`. The fallback is pure C shift/negate arithmetic.
- **`mbedtls_ct_uint_ne/eq/lt/ge/...`** are built on `ct_bool` and XOR. For example, `ct_uint_ne` is `ct_bool(x ^ y)`.
- **Selection and conditional copy** (`mbedtls_ct_if`, `ct_uint_if`, `ct_memcpy_if`) use masks: `(a & mask) | (b & ~mask)`. `mbedtls_ct_memcpy_if` does this word-at-a-time.
- **`mbedtls_ct_memcpy_offset`** reads every candidate offset in `[offset_min, offset_max]` and uses `ct_memcpy_if` to pick the one that matches, so the access pattern depends on the range, not the secret offset.
- **`mbedtls_ct_memcmp`** XORs every byte through `volatile` pointers and ORs the differences into one accumulator, so the loop cannot exit early. The index records that it is constant-time with respect to the data but not with respect to `n`.

The `asm volatile` blocks are the real enforcement. The compiler cannot reason about their contents, so it cannot turn the mask into a branch. `mbedtls_ct_compiler_opaque(x)` hides the value of `x` from the optimiser. With assembly it is an empty `asm volatile` that takes and returns `x`. Without assembly it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` zero, so the compiler must load it at run time.

## What happens on a compiler that cannot support it

There is no build error. The selection is preprocessor-based:

1. `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is on and the compiler is GCC-like (`__GNUC__`) or ARMCC.
2. Per-architecture macros (`MBEDTLS_CT_X86_64_ASM`, `_X86_ASM`, `_ARM_ASM`, `_AARCH64_ASM`) pick a specific asm block based on `__x86_64__`/`__amd64__` and similar.
3. Otherwise the code falls back to the portable C version.

The fallback's comment says that as of May 2023, trunk GCC, Clang and MSVC v19 do not turn that C into branches or conditional instructions. That is an observation about specific compiler versions, not a guarantee. The `SECURITY.md` "Caveats" section says compilers can introduce timing side channels in code meant to be constant-time, and that the project will generally treat an exploitable one as a vulnerability when it appears with a common compiler at a common setting. The index cuts that sentence off, so I cannot quote its full scope.

The one hard refusal is in `mbedtls_ct_memcmp`: `#error` if `int` is narrower than 32 bits, because the final truncating cast could drop the top-half bits and change the result.

Verification is by testing rather than by the compiler. `tests/scripts/components-configuration-crypto.sh` defines `test_with_valgrind_constant_time`, which runs a small set of dedicated constant-time tests under Valgrind. The architecture docs also mention Valgrind memory poisoning for constant-flow testing.

## How far it reaches

| Area | Uses the facility? | Evidence in the index |
|---|---|---|
| `bignum_core` | Yes | `mbedtls_mpi_core_lt_ct`, `ct_mpi_uint_if` (called from `cond_assign` and `cond_swap`); public `mbedtls_mpi_lt_mpi_ct`, `mpi_core_check_zero_ct` |
| `nist_kw` unwrap | Yes | Calls `mbedtls_ct_memcmp_partial` |
| TLS record/CBC padding | Probably, not confirmed | `ct_memcpy_offset` and `ct_error_if_else_0` have unresolved callers in the index, so I cannot name the SSL call sites |
| `mbedtls_ct_memcmp` itself | Unknown | Index marks it `orphan`, with only self-recursion recorded; the index flags unresolved receiver calls, so this is not proof of no callers |
| PSA verify functions | Specified, not via this module | `psa_mac_verify_finish`, `psa_hash_verify`, `psa_aead_verify` and `psa_key_derivation_verify_bytes` require a best-effort constant-time comparison. `docs/psa-transition.md` says PSA has no equivalent of the `mbedtls_ct_` utilities |
| `p256-m` (3rdparty) | Separate implementation | Its own design: Fermat inversion for constant-time modular inverse, and a `MUL64_IS_CONSTANT_TIME` switch for platforms with and without constant-time 32×64 multiply |

`SECURITY.md` also states that Mbed TLS makes no guarantee against local non-timing side channels. Its network-timing scope is a separate matter.

## What I could not settle from the index

- The exact preprocessor layout of `constant_time_impl.h`. The index records the Arm 32-bit gate on a block spanning lines 289–539, but I did not read the surrounding `#if` structure.
- Which SSL and X.509 paths call the CT primitives, since their callers are unresolved.
- Whether `mbedtls_ct_memcmp` has callers outside the index's resolution.

Reading the call sites in `ssl_msg.c` and `ssl_tls.c` (for the padding path) and `psa_crypto*.c` (for the verify path) would close these.