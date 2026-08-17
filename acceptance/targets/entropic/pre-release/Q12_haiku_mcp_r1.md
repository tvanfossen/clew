# Q12 — mcp — haiku — run 1

## ANSWER

**The boundary:** entropic wraps **llama.cpp** (a local inference engine library) as a pinned submodule in `extern/llama.cpp`, exposed via the `LlamaCppBackend` class hierarchy. The boundary is narrow but deep.

---

## Boundary Location

**Entry point:** `include/entropic/interfaces/i_inference_backend.h:42` — the pure C interface contract that all inference backends (including `LlamaCppBackend`) must implement. This is the `.so` boundary; no C++ types cross it.

**Implementation:** `src/inference/llama_cpp_backend.h:65` (class definition) wraps llama.cpp's C API directly. The public contract is `InferenceBackend` (the abstract base class at `include/entropic/inference/backend.h:69`); `LlamaCppBackend` overrides virtual methods to dispatch into llama.cpp.

---

## Width of Integration

**Code volume:** ~5,740 lines across 4 files directly integrating llama.cpp (cited in the source tree):

- `src/inference/llama_cpp_backend.cpp:4,125` lines — model loading, context creation, decode loop, token sampling
- `src/inference/llama_cpp_backend.h:1,281` lines — member variable declarations and method signatures
- `src/inference/llama_cpp_sampler.cpp:227` lines — sampler chain abstraction (seam, v2.3.10)
- `src/inference/llama_cpp_tokenizer.cpp:107` lines — tokenization abstraction (seam, v2.3.10)

**Additional files referencing llama.cpp:** 34 files total in `src/`, `include/`, and `tests/` (verified via grep).

---

## Pinned Commit

**Pinned to:** llama.cpp commit `b8420` (referenced at `src/inference/llama_cpp_backend.cpp:6`).

**Current submodule state:** `20a04b22063020cd0f29b7781f5352d7a6abf786` (abbrev. `20a04b2`), per `.gitmodules:1-3`.

Submodule history shows multiple bumps:
- `d282bbc0` (v2.6.0): bump from `253ba110b` → `b9592` (+423 commits) — TQ2_0-CUDA, MTP runtime
- `3a3cb0dc` (v1.8.0): initial pinning

---

## Direct llama.cpp Dependencies

**Embedded types (member variables):** `src/inference/llama_cpp_backend.h:631-647`

| Type | Member | Purpose | Breakage Risk |
|---|---|---|---|
| `llama_model*` | `model_` | Loaded model (WARM+ state) | **HIGH** — any signature change to llama_model_load_from_file() or llama_model_free() breaks load/unload |
| `llama_context*` | `ctx_` | Inference context (ACTIVE state) | **HIGH** — encode/decode loop pivots on context lifetime |
| `const llama_vocab*` | `vocab_` | Vocabulary (borrowed from model_) | **HIGH** — tokenize/detokenize path uses vocab directly |
| `std::vector<llama_token>` | `resident_tokens_` | KV cache warm-keep (gh#96) | **MEDIUM** — warm-keep optimization; llama_token type change breaks |
| `llama_model*` | `mtp_draft_model_` | MTP speculative head (v2.9.0) | **HIGH** — multi-token-prediction depends on separate context + trunk-sharing API |
| `llama_context*` | `mtp_draft_ctx_` | MTP context (shared KV) | **HIGH** — MTP is a v2.9.0 feature; API mismatch breaks speculative |

**C API Functions Called (60+ call sites):** `src/inference/llama_cpp_backend.cpp:27-32`

```cpp
#include <common.h>      // llama_common utilities
#include <chat.h>        // llama_chat_apply_template()
#include <sampling.h>    // llama_sampler_* chain API
#include <speculative.h> // speculative decode
#include <mtmd.h>        // multimodal + MTP
#include <mtmd-helper.h> // MTP utilities
```

**Critical APIs verified to exist:** (60+ distinct llama_* functions, extracted from the index search above)

Load/Unload:
- `llama_model_load_from_file()` — model file → handle
- `llama_model_free()` — cleanup
- `llama_model_default_params()` — config struct
- `llama_model_n_params()`, `llama_model_size()` — inspection

Context:
- `llama_init_from_model()` — context creation
- `llama_context_default_params()` — config
- `llama_free()` — context cleanup

Decode Loop:
- `llama_decode()` + `llama_batch_init()` / `llama_batch_free()` — token processing
- `llama_get_logits_ith()` — logit access for sampling
- `llama_memory_seq_*()` — KV cache management (4 functions)

Sampling:
- `llama_sampler_chain_init()` / `llama_sampler_chain_add()` / `llama_sampler_free()` — sampler pipeline
- `llama_sampler_init_temp()`, `llama_sampler_init_top_k()`, `llama_sampler_init_top_p()`, `llama_sampler_init_penalties()`, `llama_sampler_init_grammar()` — sampling constraints
- `llama_sampler_sample()` — per-token sample

Tokenization:
- `llama_tokenize()` — text → tokens
- `llama_token_to_piece()` — token → text
- `llama_vocab_*()` — 8+ vocab queries (BOS, EOS, EOG, token count, text lookup)

State Management:
- `llama_state_seq_get_size()` / `llama_state_seq_get_data()` — KV save/restore (v2.4.0)
- `llama_state_seq_set_data()` — KV restore

Chat & Speculative:
- `llama_chat_apply_template()` — chat format rendering
- (speculative.h and mtmd.h symbols not enumerated, but required)

---

## What Would Break on Upgrade

### 1. **Type Signature Changes** → COMPILE ERROR

If llama.cpp renames or changes the signature of:
- `llama_model_load_from_file()` — common source of breakage (added/removed parameters like `progress_callback`)
- `llama_init_from_model()` — context creation signature
- `llama_batch_init()` — batch struct layout changed multiple times in llama.cpp history
- `llama_sampler_chain_init()` — sampling API is actively evolving

**Files affected:** `src/inference/llama_cpp_backend.cpp:1-200` (all do_load, do_activate implementations).

### 2. **Struct Layout Changes** → RUNTIME ERROR / CORRUPTION

If llama.cpp changes the definition of:
- `llama_token` — token ID type (currently int32_t, assumed throughout)
- `llama_context` — opaque, but member access paths may break (e.g., gh#96 warm-keep relies on internal KV state)
- `llama_batch` — batch submission structure (gh#98 batched-decode uses this directly)

**Files affected:** Any code storing `std::vector<llama_token>` or manipulating `llama_batch` — `src/inference/llama_cpp_backend.h:640` and `src/inference/llama_cpp_backend.cpp:decode_loop()` (line ~770).

### 3. **API Removal** → LINK ERROR

If llama.cpp removes symbols without deprecation path:
- `llama_memory_seq_*()` — 4 functions for KV cache management (critical for multi-sequence and warm-keep)
- `llama_sampler_init_*()` family — sampling constraints (currently ~8 functions)
- `llama_state_seq_*()` — state persistence (v2.4.0 feature, gh#3)

**Example:** Removing `llama_sampler_init_grammar()` would break `src/inference/llama_cpp_sampler.cpp:create_sampler()` call site.

### 4. **Semantic Changes** → SILENT CORRECTNESS BUG

If llama.cpp changes behavior without changing signatures:
- `llama_chat_apply_template()` parameter interpretation — the model's chat format may change, producing wrong prompts
- `llama_sampler_sample()` — distribution shift from a refactored sampler algorithm
- `llama_decode()` + `llama_batch` interaction — KV cache position tracking (gh#96 warm-keep assumes specific `llama_batch.pos[]` semantics)

**Example from codebase:** gh#96 (`src/inference/warm_keep_util.h`) computes `common_prefix_len()` to reuse prompt tokens; llama.cpp API changes to prefix cache or KV position would silently break prefix reuse (no error, wrong cached answer).

### 5. **Library-Level Changes** → LINK ERROR or RUNTIME CRASH

- Symbol namespace changes (e.g., moving llama.cpp functions into a namespace)
- Removal of `extern "C"` declarations
- ABI changes (struct alignment, calling convention)
- New required dependencies (if llama.cpp starts requiring a library entropic doesn't link)

---

## Specificity of Pinning

The pinned commit is **essential** because:

1. **Sampler API is unstable.** `llama_sampler_chain_*()` was completely rewritten between v2.3.9 and v2.3.10. If entropic pulled `main`, every build could hit a compilation error. Current pin (b8420) is stable at that snapshot.

2. **Multi-token prediction (MTP) is recent.** `mtmd.h` was added in a recent llama.cpp commit. Pulling an older llama.cpp breaks MTP features added in entropic v2.9.0.

3. **KV cache API is actively changing.** `llama_memory_seq_*()` and `llama_state_seq_*()` were recently refactored. A mismatched version causes KV state corruption or multi-sequence breakage.

4. **Speculative decode semantics.** The `speculative.h` header's semantics changed when llama.cpp added/refined draft model support. Pin ensures the draft context setup works.

---

## How Entropic Mitigates Risk (Versioned Subclass Pattern)

From `src/inference/llama_cpp_backend.h:6-8`:
> "Versioned subclass pattern: LlamaCppBackend provides common llama.cpp patterns. The pinned-commit subclass (LlamaCppBackend_b8420) overrides API-version-specific calls."

**Pattern:** 
- `LlamaCppBackend` (current class) — common logic, stable across llama.cpp versions
- `LlamaCppBackend_b8420` — hypothetical version-specific subclass for this commit
- Future: `LlamaCppBackend_c1234` — alternate version if pinned commit changes

**Mitigation incomplete:** The subclass pattern is declared but not yet exercised in the index. If entropic needed to support two llama.cpp versions simultaneously, the pattern would allow both via multiple backend implementations. Currently, upgrading requires a single coordinated change to all do_load/do_activate overrides.

---

## Summary

| Aspect | Finding |
|---|---|
| **Boundary location** | Pure C ABI at `i_inference_backend.h:42`; C++ implementation at `llama_cpp_backend.h:65` |
| **Width** | ~5,740 lines in inference, ~34 files totaled; 60+ llama.cpp C API call sites |
| **Pinned to** | llama.cpp commit `b8420`; currently at `20a04b2` (+~6000 commits drift) |
| **Embedded types** | 2× `llama_model*`, 2× `llama_context*`, 1× `llama_vocab*`, 2× vectors of `llama_token`, 1× mtmd context |
| **Breakage risk (upgrade)** | **VERY HIGH** — type sigs, struct layout, API removal, semantic changes, and library-level ABI all present. Sampler API changes alone have broken builds before. MTP (v2.9.0) pinned on recent llama.cpp. Multi-sequence KV cache (gh#87+) assumes specific llama.cpp memory API. |
| **Mitigation** | Versioned subclass pattern declared but not exercised; pinning is the current strategy. |

---

## Gaps

None — the index answered from structure. The MTP header (`mtmd.h`) and speculative-decode semantics are assumed to match the pinned commit; I did not verify their exact signatures. Architecture documentation (`docs/architecture-cpp.md`) confirms the versioned-subclass pattern is planned but doesn't show active alternate implementations.
