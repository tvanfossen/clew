# Q12 — src — sonnet — run 1

Good, I have a thorough picture from the source tree. Now compiling the answer.

## Answer

**The boundary — where and how**

entropic vendors `llama.cpp` as a **git submodule** at `extern/llama.cpp` (`.gitmodules:1-3`), pinned to a specific commit `20a04b22063020cd0f29b7781f5352d7a6abf786` (tag `gguf-v0.19.0-840-g20a04b220`) per `git submodule status`. The build pulls it in via `add_subdirectory(extern)` (`CMakeLists.txt:134`).

The crossing point on entropic's side is almost entirely inside **one library target**, `src/inference/` (built as `entropic-inference-{cpu,cuda,vulkan}`, `src/inference/CMakeLists.txt:8-72`). It links three llama.cpp-provided targets — `llama`, `llama-common`, `mtmd` (`src/inference/CMakeLists.txt:63-71`) — and pulls extra vendor include paths for `common.h`/`sampling.h`/`speculative.h` and `stb_image.h` (`src/inference/CMakeLists.txt:58-60`).

Concretely, the vendor API is touched in these files (`grep` for `#include <llama.h>` / `<common.h>` / `<mtmd.h>` / `<chat.h>`):
- `llama_cpp_backend.{h,cpp}` (4,125 + 1,281 lines) — the core wrapper: model/context lifecycle, decode loop, KV/session state, warm-keep, MTP/speculative dispatch. Includes `<llama.h>`, `<common.h>`, `<mtmd.h>`, `<mtmd-helper.h>` (`src/inference/llama_cpp_backend.h:33`, `src/inference/llama_cpp_backend.cpp:27,31-32`).
- `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}` — sampler-chain and tokenizer wrappers around `<llama.h>`.
- `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, `secondary_model_loader.cpp`, `inference_c_api.cpp`, `interface_factory.cpp` — all `#include <llama.h>` or the internal `llama_cpp_backend.h` directly.
- `tool_call_markers.h` includes `<chat.h>` (llama.cpp's `common_chat` parsing layer) directly (`src/inference/tool_call_markers.h:30`).

Elsewhere in the tree the coupling is deliberately narrow: `src/config/loader.cpp`, `src/core/response_generator.cpp`, and `src/facade/entropic.cpp` include `llama_cpp_backend.h` (entropic's own header), not llama.cpp headers directly — they sit above the `InferenceBackend` abstraction (`include/entropic/inference/backend.h`), which the file doc explicitly frames as an 80/20 split: the concrete base class owns lifecycle/locking/logging (`include/entropic/inference/backend.h:8-33`) and `LlamaCppBackend` supplies "common llama.cpp patterns (15% layer)" (`src/inference/llama_cpp_backend.h:56-64`).

**How wide**

A `grep` for `llama_[a-zA-Z0-9_]+(` across `src/` and `include/` finds **62 distinct llama.cpp C-API call sites** (`llama_decode`, `llama_batch_init`, `llama_sampler_chain_add`, `llama_memory_seq_rm`, `llama_model_load_from_file`, `llama_adapter_lora_init`, etc.). On top of the plain `llama.h` surface, entropic also depends on:
- `mtmd`/`mtmd-helper` (multimodal, forward-declared opaque `mtmd_context`/`mtmd_bitmap` at `src/inference/llama_cpp_backend.h:44-52`, full types only pulled in from the `.cpp`),
- `common/` helpers (`common.h`, `sampling.h`, `speculative.h` — `src/inference/CMakeLists.txt:60`),
- `chat.h`/`common_chat` (PEG tool-call parser, `tool_call_markers.h:14-16`),
- `stb_image.h` vendored under `extern/llama.cpp/vendor` for image preprocessing.

So the boundary is one build target wide (`src/inference/`) but touches several sub-APIs of llama.cpp (core inference, sampling, chat template/tool-call parsing, multimodal, speculative decoding) — not just the narrow `llama_decode` surface.

**What would break on an upstream bump — explicit fragility notes in the source itself:**

1. **`speculative_compat.h`/`.cpp`** — mirrors a check that used to be a public symbol (`common_speculative_is_compat`) at an older pin (`7f2cbd9a4`) but became a file-private static (`common_speculative_are_compatible`) at the current pin (`253ba110b`), forcing entropic to reimplement the logic rather than call it (`include/entropic/inference/speculative_compat.h:8-15`). A future upstream refactor of that private function silently desyncs entropic's copy.
2. **`mtp_envelope.h`** — the correctness proof for lossless MTP speculative decoding at any temperature depends on an unenforced upstream invariant: that `common_speculative_impl_draft_mtp::draft()` in `extern/llama.cpp/common/speculative.cpp` always proposes the argmax and never reads `cur_p->selected`. The comment states plainly: "If a future extern/llama.cpp pin bump changes draft() to honor `cur_p->selected` instead of `data[0]`, this proof no longer holds and the guard must be reinstated" (`src/inference/mtp_envelope.h:42-45`).
3. **`tool_call_markers.h`** — tool-call close markers are hardcoded to track `extern/llama.cpp/common/chat-peg-parser.cpp:442-443`'s `section_end` values, and the comment says they "MUST be re-checked on a llama.cpp pin bump" (`src/inference/tool_call_markers.h:14-17`).
4. **gh#108 flash_attn guard** — was removable only because upstream PR #25148 ("CUDA: fix Gemma E4B MTP FlashAttention") landed and the pin was bumped past it; the reverse (a pin *rollback*, or a future regression) would reopen the abort this guard existed to prevent (`src/inference/mtp_envelope.h:19-25`, `src/inference/llama_cpp_backend.cpp:3862-3868`).
5. **Hybrid/recurrent (SSM) architecture guard** in `speculative_compat.h:24-38` — upstream "does NOT self-disable" for Mamba/RWKV/hybrid targets at this pin; entropic's extra gate is compensating for an upstream gap that could change (fixed or made moot) on a future version.
6. **Prefill/warm-keep path** (`llama_cpp_backend.cpp:2148-2160`) — hybrid/recurrent architectures are forced onto the plain full-prefill path because "the partial seq_rm warm-keep needs... is the only correct path for these archs **at this llama.cpp pin**" — an explicit statement that upstream KV/memory semantics for SSM models are pin-dependent.
7. **Channel-stripping (`<|channel>...`) workaround** (`llama_cpp_backend.cpp:1305-1308`) exists only because "common_chat has no channel parser at this pin" — an upstream parser addition could make this dead code or conflict with it.

## Gaps

- I did not build the project, so I cannot confirm the exact llama.cpp API surface entropic actually links against differs from what a newer pinned commit would expose (i.e., I traced *stated* fragility from code comments, not by diffing against a newer llama.cpp checkout — no second tree/version was available to diff against).
- `LlamaCppBackend_b8420`, mentioned in `llama_cpp_backend.h:8` as "the pinned-commit subclass," does not appear to exist under that name anywhere in `src/` or `include/` — the versioned-subclass pattern described in the doc comment appears aspirational/historical rather than currently implemented; I could not find where (if anywhere) it lives.
- I did not exhaustively audit `python/` or `examples/` trees for additional llama.cpp coupling beyond the C++ core (time-boxed to `src/`/`include/`, which the question's "boundary width" seems aimed at).
