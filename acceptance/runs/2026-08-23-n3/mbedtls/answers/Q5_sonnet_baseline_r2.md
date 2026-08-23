I have enough now to answer directly from what's in the repo.

## The mechanism: hand-written inline assembly per architecture, C fallback otherwise

mbedtls doesn't trust the compiler to preserve constant-time behavior for secret-dependent branches/selects — optimizers routinely turn `cond ? a : b`-style C into a conditional branch or a conditional move depending on mood, register pressure, and optimization level, any of which can leak timing. So the library builds a small set of primitives — `mbedtls_ct_bool`, `mbedtls_ct_if`, `mbedtls_ct_uint_lt`, etc. (`library/constant_time_internal.h`, `library/constant_time_impl.h`) — and for the architectures it can target with GNU inline asm, it hand-writes the actual instruction sequence:

- **AArch64**: `neg`/`orr`/`asr` to turn an integer into an all-ones/all-zeros mask (`mbedtls_ct_bool`), and `and`/`mvn`/`and`/`orr` to select between two values using that mask (`mbedtls_ct_if`) — pure bitwise ops, no `cmp`+branch, no `csel`.
- **ARM/Thumb**: the same idea with `negs`/`orrs`/`asrs`, carefully switched to unified syntax because Thumb-1 only accepts the `s`-suffixed forms while divided syntax needs the plain ones, and reverted afterward on old GCC because unified syntax otherwise leaks into surrounding asm blocks (`library/constant_time_impl.h:96-117`).
- **x86 / x86-64**: `mov`/`neg`/`or`/`sar` sequences, again all bitwise/arithmetic instructions, no branch, no `cmov` even (a `cmov` is technically constant-time on modern Intel/AMD but they don't rely on the compiler emitting it — they emit the mask arithmetic directly).

This is gated behind `MBEDTLS_CT_ASM`, defined only when `MBEDTLS_HAVE_ASM` is set, the compiler is GNU-inline-asm-capable (`__GNUC__`, explicitly excluding armcc5's `--gnu` mode which defines `__GNUC__` but can't parse extended asm), and the target arch is one of arm/thumb/aarch64/x86/x86-64. There's also a `mbedtls_ct_compiler_opaque()` helper that does `asm volatile ("" : [x] "+r" (x) :)` — a classic "opaque" barrier that forces the value through a register and tells the compiler it may have changed, so it can't fold or hoist computations across it based on a known value.

## What happens with no assembly support

If none of that applies (MSVC, an unsupported architecture, `MBEDTLS_HAVE_ASM` off, etc.), everything falls back to plain C — and the fallback is designed with the same "constant-time on real compilers" intent even though it can't be *guaranteed* the way asm can:

- `mbedtls_ct_compiler_opaque` becomes `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global always equal to 0 (`library/constant_time.c:29`) — XOR-ing against a volatile forces a real memory load the compiler can't constant-fold away, achieving the same "the compiler must treat this as unknown" effect as the asm barrier, just less cheaply.
- `mbedtls_ct_bool` becomes bit-twiddling: `y = (-xo) | -(xo >> 1)`, then extract the sign bit, then negate — mask generation with only arithmetic/logical ops, no comparison.
- `mbedtls_ct_if` becomes `(condition & if1) | (~condition & if0)`.

The header is explicit that this is a best-effort, not a proof: the comment says the plain-C version "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19 as of May 2023" — i.e., it's an empirically-verified property of specific compiler versions at specific dates, not a language guarantee. So on an unsupported compiler you get weaker assurance (a compiler *could* legally recognize the idiom and re-branch it) but it's still the best C-level approximation available, and it's the same code path used for every mbedtls-supported architecture that isn't arm/aarch64/x86/x86-64.

## How far it reaches

This isn't confined to RSA padding checks. `grep` for the `mbedtls_ct_*` primitives across `library/` turns up 25 files, spanning:

- **Bignum core**: `bignum.c`, `bignum_core.c`, `bignum_mod_raw.c` — the arbitrary-precision arithmetic underneath RSA/DHM/ECC.
- **Public-key**: `rsa.c` (PKCS#1 padding/decryption, the classic Bleichenbacher-oracle surface).
- **Symmetric/AEAD**: `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c`.
- **Cipher abstraction**: `cipher.c`.
- **PSA crypto**: `psa_crypto.c`, `psa_crypto_mac.c`, `psa_crypto_cipher.c`, `psa_crypto_driver_wrappers.h`.
- **TLS record/handshake layers**: `ssl_msg.c`, `ssl_tls.c`, `ssl_tls12_client.c`, `ssl_tls12_server.c`, `ssl_tls13_server.c`, `ssl_tls13_generic.c`, `ssl_cookie.c` — this is where MAC-then-decrypt padding-oracle timing (Lucky13-class issues) actually gets defended.

Beyond the boolean/select primitives, `library/constant_time.c` also provides block-level operations built on the same masking idea: `mbedtls_ct_memcmp` (constant-time buffer compare, not time-constant in length `n`, only in contents), `mbedtls_ct_memcpy_if` (conditional copy without branching on the condition), `mbedtls_ct_memmove_left`, and `mbedtls_ct_zeroize_if`. So the facility covers three levels — single-bit conditions, scalar selects, and whole-buffer conditional copy/compare — and it's threaded through essentially every place in the library that makes a decision based on secret data: MAC/padding validation in TLS and AEAD modes, modular-exponentiation-adjacent bignum comparisons, and RSA decryption/padding. It is explicitly *not* limited to one algorithm; it's the library's general "secret-dependent decision" primitive, used wherever a `bool`/`if`/`memcmp` would otherwise touch secret data.
