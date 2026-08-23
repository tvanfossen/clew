## The mechanism, from the bottom up

mbedtls's constant-time layer lives almost entirely in three files: `include/mbedtls/constant_time.h` (public API), `library/constant_time_internal.h` (the `mbedtls_ct_condition_t`/`mbedtls_ct_uint_t` types and `MBEDTLS_CT_TRUE`/`MBEDTLS_CT_FALSE`), and `library/constant_time_impl.h` (the actual instruction-level primitives, inlined). Everything else in the library that needs to avoid secret-dependent branches is built on top of a small set of primitives defined there: `mbedtls_ct_bool`, `mbedtls_ct_if`/`mbedtls_ct_uint_if`, `mbedtls_ct_bool_and/or/not/ne`, `mbedtls_ct_memcpy_if`, `mbedtls_ct_zeroize_if`, `mbedtls_ct_memcmp`, and the `mbedtls_ct_uint_{eq,ge,gt,lt,le,ne}` comparison family.

**Enforcement at the instruction level is inline assembly, per architecture, hand-picked to avoid any conditional-branch or conditional-move opcode a compiler might otherwise choose to synthesize.** `mbedtls_ct_bool` (the function that turns "is this word zero or not" into an all-ones/all-zeros mask) has four architecture-specific bodies, selected by macro:

- **AArch64** (`MBEDTLS_CT_AARCH64_ASM`): `neg`/`orr`/`asr` — negate, OR with the original, then arithmetic-shift the sign bit across the whole word.
- **32-bit ARM** (`MBEDTLS_CT_ARM_ASM`): the Thumb/ARM equivalent (`negs`/`orrs`/`asrs`), explicitly clobbering the flags register so the compiler can't reuse a stale condition code.
- **x86-64** (`MBEDTLS_CT_X86_64_ASM`): `mov`/`neg`/`or`/`sar $63`.
- **32-bit x86** (`MBEDTLS_CT_X86_ASM`): the 32-bit analog with `sar $31`.

All four are `asm volatile` blocks — `volatile` so the compiler can't discard or reorder them, and none of them contains a jump, `cmov`, `sete`, or any instruction whose micro-op count or port usage depends on the data value. The mask-generation only ever uses arithmetic/logical ops with fixed latency regardless of operand value.

The second load-bearing primitive is `mbedtls_ct_compiler_opaque`, used to break the compiler's *dataflow* reasoning even when no branch-avoidance asm is needed. It's just `asm volatile ("" : [x] "+r" (x) :)` — an empty asm statement that reads and rewrites `x` through a register constraint. This gives the optimizer no instructions to look at, so it cannot prove anything about `x`'s value (in particular, it can't fold `mbedtls_ct_compiler_opaque(1)` back down to a compile-time constant `1`, which matters because a compile-time-known condition is exactly what would let the compiler decide the surrounding "constant-time" logic is dead code and re-introduce a branch).

## What happens when the compiler/architecture can't support it

There's an explicit, tiered fallback, gated by `MBEDTLS_HAVE_ASM && (__GNUC__ || __ARMCC_VERSION)` combined with an architecture check (`__aarch64__`, `__arm__`+32-bit, `__amd64__`/`__x86_64__`, or 32-bit `__i386__`-class). If none of that matches — no inline-asm-capable compiler, or an architecture with no hand-written masking sequence — every primitive drops to a **plain C fallback**, documented in-line as verified (as of the comment, May 2023) to *not* get compiled into a branch or conditional-move by trunk clang, gcc, or MSVC:

```c
const mbedtls_ct_uint_t xo = mbedtls_ct_compiler_opaque(x);
mbedtls_ct_int_t y = (-xo) | -(xo >> 1);      // sign bit set iff x != 0
y = (((mbedtls_ct_uint_t) y) >> (MBEDTLS_CT_SIZE - 1));
return (mbedtls_ct_condition_t) (-y);
```

So the guarantee on an unsupported compiler is downgraded from "this instruction sequence has no data-dependent branch" (verified by inspection of the emitted asm) to "this C expression has been observed not to get compiled into a branch on the compilers we checked" — a weaker, empirical guarantee that could in principle regress with a future compiler version, which is exactly why the asm paths exist at all for the architectures that matter most. `mbedtls_ct_compiler_opaque` itself has the same shape: the non-asm fallback is `return x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a non-`const` global the compiler can't fold, which is a weaker opacity guarantee than the empty-asm trick but the best available without inline asm.

Word size is handled the same way: `MBEDTLS_CT_SIZE_32`/`MBEDTLS_CT_SIZE_64` (defined in `constant_time_internal.h`, gating 12 and 9 sites respectively in `constant_time_impl.h`/`.c`) pick which asm variant and which mask width (`uint32_t` vs `uint64_t`) apply, so the asm selection is a compiler×arch×word-size product, not a single switch.

## How far it reaches into the rest of the library

The index shows this isn't confined to one module — it's the standard tool for every place a secret-dependent comparison or copy would otherwise show up as a branch:

- **Bignum/ECC core** — `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_core_lt_ct` (`bignum_core.h`), `mbedtls_mpi_lt_mpi_ct` and `mbedtls_ct_mpi_sign_if` (`bignum.c`), and `mbedtls_mpi_gcd_modinv_odd` (`bignum_internal.h`, wrapping a constant-time GCD/modinv). `mbedtls_mpi_lt_mpi_ct`'s body is a direct consumer of the primitives — `mbedtls_ct_bool`, `mbedtls_ct_bool_and/or/not/ne`, `mbedtls_ct_size_if_else_0`, `mbedtls_ct_uint_if_else_0` — to compare signed MPIs without ever branching on the sign or magnitude.
- **RSA** — `mbedtls_ct_rsaes_pkcs1_v15_unpadding` in `rsa.c` calls `mbedtls_ct_zeroize_if`, which is exactly the Bleichenbacher-oracle defense: PKCS#1 v1.5 unpadding must not leak, via timing or branching, whether the padding was well-formed.
- **TLS record layer** — `mbedtls_ct_hmac` in `ssl_msg.c`, the classic Lucky-13-style constant-time MAC check on CBC records.
- **Base64** — `mbedtls_ct_base64_dec_value` / `mbedtls_ct_base64_enc_value` in `base64.c`, avoiding table-lookup timing variance.
- **PSA layer** — the prose index shows `psa_aead_verify`, `psa_mac_verify_finish`, and `psa_key_derivation_verify_bytes` all documenting a constant-time comparison requirement at the API-contract level, even though (per `docs/psa-transition.md`) the PSA API itself has no direct equivalent to `constant_time.h` and instead relies on the legacy layer's `mbedtls_ct_*` underneath.

So the reach is: one small hand-verified assembly core → a typed condition/mask abstraction (`mbedtls_ct_condition_t`, `mbedtls_ct_uint_t`) → generic constant-time primitives (compare, select, memcpy, memcmp, zeroize) → consumed independently by bignum/ECC, RSA padding, TLS MAC verification, and base64, with the PSA crypto API's own doc comments asserting the same constant-time contract at the interface boundary even though its implementation is layered on the legacy `mbedtls_ct_*` machinery rather than reimplementing it.

One honest gap: the index resolves call edges by name/AST, and `dossier` on `mbedtls_ct_memcmp` returned no callers — that's very likely a resolution artifact (cross-TU calls not captured by the doxygen/AST layer here) rather than evidence the function is unused; I'd want to grep source directly to enumerate its call sites, which the index alone can't give me.
