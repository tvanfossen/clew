# Q12 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic && find . -maxdepth 2 -type d | grep -v '^\./\.git' | sort
- **got:** . ./.claude ./.claude/proposals ./.claude/reports ./cmake ./data ./data/grammars ./data/prompts ./data/schemas ./data/tools ./docs ./docs/generated ./.entropic ./examples ./examples/explorer ./examples/headless ./example…

### 2. `Bash`
- **asked:** command=cat .gitmodules 2>/dev/null; echo "---"; git submodule status 2>/dev/null; echo "---"; ls extern 2>/dev/null; ls third_party 2>/dev/null
- **got ⚠ error:** Exit code 2 [submodule "extern/llama.cpp"] 	path = extern/llama.cpp 	url = https://github.com/ggml-org/llama.cpp.git ---  20a04b22063020cd0f29b7781f5352d7a6abf786 extern/llama.cpp (gguf-v0.19.0-840-g20a04b220) --- CMakeL…

### 3. `Bash`
- **asked:** command=ls src/inference && echo "---" && wc -l src/inference/*.cpp src/inference/*.h 2>/dev/null | tail -30
- **got:** adapter_manager.cpp adapters backend.cpp batch_util.h CMakeLists.txt grammar_registry.cpp image_preprocessor.cpp inference_c_api.cpp interface_factory.cpp llama_cpp_backend.cpp llama_cpp_backend.h llama_cpp_sampler.cpp l…

### 4. `Bash`
- **asked:** command=grep -rl "llama.h\|llama_\|#include \"llama" src include --include="*.h" --include="*.cpp" --include="*.hpp" -l | sort
- **got:** include/entropic/entropic.h include/entropic/inference/adapter_manager.h include/entropic/inference/grammar_registry.h include/entropic/inference/orchestrator.h include/entropic/inference/sampler.h include/entropic/infer…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/llama_cpp_backend.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file llama_cpp_backend.h 4	 * @brief LlamaCppBackend — llama.cpp C API integration. 5	 * 6	 * Versioned subclass pattern: LlamaCppBackend provides common llama.cpp 7	 …

### 6. `Bash`
- **asked:** command=grep -rhoE '\bllama_[a-zA-Z0-9_]+\s*\(' src include | sed -E 's/\s*\($//' | sort -u | wc -l echo "---sample---" grep -rhoE '\bllama_[a-zA-Z0-9_]+\s*\(' src include | sed -E 's/\s*\($//' | sort -u | head -40 echo "--- interface abstraction ---" find src/inference -iname "*interface*" -o -iname "*backend*" | sort
- **got:** 62 ---sample--- llama_adapter_lora_free llama_adapter_lora_init llama_batch_free llama_batch_get_one llama_batch_init llama_chat_apply_template llama_context llama_context_default_params llama_context_ptr llama_decode ll…

### 7. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic grep -rl "LlamaCppBackend_" src include | sort echo "---" grep -n "class LlamaCppBackend_" -r src include echo "--- CMake pin ---" grep -rn "GIT_TAG\|20a04b2\|llama.cpp" CMakeLists.txt cmake/*.cmake 2>/dev/null | head -30
- **got:** src/inference/llama_cpp_backend.h --- --- CMake pin --- CMakeLists.txt:71:        # picks 52 (lowest supported for CUDA 12), and llama.cpp's

### 8. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/interface_factory.cpp
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file interface_factory.cpp 4	 * @brief InferenceInterface factory — bridges orchestrator to C callbacks. 5	 * @version 2.0.1 6	 */ 7	 8	#include <entropic/inference/in…

### 9. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic grep -n "b8420\|pinned\|PINNED\|class.*Backend" src/inference/llama_cpp_backend.h | head -40 echo "---" find src include -iname "*b8420*" -o -iname "*pinned*" echo "--- InferenceBackend base ---" find include -iname "backend.h" cat include/entropic/inference/backend.h | head -60
- **got:** 6: * Versioned subclass pattern: LlamaCppBackend provides common llama.cpp 7: * patterns (decode loop, sampler chain, tokenization). The pinned-commit 8: * subclass (LlamaCppBackend_b8420) overrides API-version-specific …

### 10. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic grep -n "llama.cpp\|add_subdirectory(extern\|GGML_\|LLAMA_" CMakeLists.txt | head -40
- **got:** 71:        # picks 52 (lowest supported for CUDA 12), and llama.cpp's 134:add_subdirectory(extern)

### 11. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic grep -rn "#include <ggml\|#include \"ggml\|#include <mtmd\|#include \"mtmd\|#include <llama\|#include \"llama\|clip.h\|common.h\|common/common" src include | sort
- **got:** src/facade/entropic.cpp:1739:    return configure_common(handle); src/facade/entropic.cpp:1788:    return configure_common(handle); src/facade/entropic.cpp:1836:    auto rc = configure_common(handle); src/facade/entropic…

### 12. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/CMakeLists.txt
- **got:** 1	# SPDX-License-Identifier: Apache-2.0 2	# ── Inference library ──────────────────────────────────────── 3	# Build variant based on compute backend. Links against llama.cpp, 4	# nlohmann/json, and spdlog. 5	# 6	# v1.8.2…

### 13. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic grep -n "GGML_VERSION\|LLAMA_BUILD\|version\|API" src/inference/speculative_compat.cpp | head -30
- **got:** 11: * @version 2.1.11 54: * @version 2.1.11 [reviewed] 82: * @version 2.1.11 100: * @version 2.1.11 122: * @version 2.1.11 145: * @version 2.1.11 174: * @version 2.1.11 211: * @version 2.1.11 241: * @version 2.1.11 [revi…

**Reasoning.** Now let me check what breaks under upgrade — signature-dependency comments, and check the git submodule pin location/history for upgrade risk notes.

### 14. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic grep -n "upgrade\|API break\|breaking\|deprecat\|GGUF_VERSION\|LLAMA_API_VERSION\|version bump\|pin\b" src/inference/*.cpp src/inference/*.h include/entropic/inference/*.h -ri | grep -iv "@version" | head -50
- **got:** src/inference/llama_cpp_backend.cpp:252:    // is "none" (pin) or "row" (small-tensor placement). 0 keeps src/inference/llama_cpp_backend.cpp:1305: * channel parser at this pin, so the block survives in `msg.content`. Th…

### 15. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/mtp_envelope.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file mtp_envelope.h 4	 * @brief Pure envelope check for the MTP speculative path (gh#108). 5	 * 6	 * MTP (multi-token-prediction) decode is correct in the greedy (temp…

### 16. `Read`
- **asked:** file_path=~/ddb-targets/entropic/src/inference/tool_call_markers.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file tool_call_markers.h 4	 * @brief gh#103 (v2.8.2): family-aware tool-call CLOSE markers, derived from 5	 *        the resolved common_chat format. 6	 * 7	 * Pure ma…

### 17. `Read`
- **asked:** file_path=~/ddb-targets/entropic/include/entropic/inference/speculative_compat.h
- **got:** 1	// SPDX-License-Identifier: Apache-2.0 2	/** 3	 * @file speculative_compat.h 4	 * @brief Tokenizer/architecture compatibility check for speculative 5	 *        decoding draft pairing. 6	 * 7	 * @par Why this lives in e…

**Reasoning.** I have enough to answer this comprehensively.

### 18. `Bash`
- **asked:** command=cd ~/ddb-targets/entropic sed -n '1290,1320p;2140,2170p;3855,3875p' src/inference/llama_cpp_backend.cpp
- **got:** append_sequential_stop(p, tool_call_close_marker());     if (p.stop.size() > before) {         logger->info("Sequential tier: tool-call close marker injected "                      "post-render (gh#105) — hard-stop at fi…

**Reasoning.** Good, I have a thorough picture from the source tree. Now compiling the answer.

## Answer

**The boundary — where and how**

entropic vendors `llama.cpp` as a **git submodule** at `extern/llama.cpp` (`.gitmodules:1-3`), pinned to a specific commit `20a04b22063020cd0f29b7781f5352d7a6abf786` (tag `gguf-v0.19.0-840-g20a04b220`) per `git submodule status`. The build pulls it in via `add_subdirectory(extern)` (`CMakeLists.txt:134`).

The crossing point on entropic's side is almost entirely inside **one library target**, `src/inference/` (built as `entropic-inference-{cpu,cuda,vulkan}`, `src/infere

---

## Final answer as submitted

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
