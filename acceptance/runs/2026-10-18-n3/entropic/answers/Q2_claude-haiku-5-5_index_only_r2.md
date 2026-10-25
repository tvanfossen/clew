**Short answer:** llama.cpp enters through a git submodule pinned at `extern/`, and it reaches well into entropic's `src/inference/` layer. Above that layer it is mostly hidden behind abstract interfaces, with a few leaks.

**How it's brought in (partly inferred)**
- The index has no CMake or git-submodule parsing, so I can't read the wiring directly. The only evidence is `src/inference/llama_cpp_backend.cpp`'s file doc, which says it is "Pinned against llama.cpp submodule b8420", and `extern/CMakeLists.txt`, which exists but has zero indexed symbols.
- Treat "submodule plus `extern/CMakeLists.txt`" as the likely mechanism, and confirm it in the build files.
- Two pins are mentioned: b8420 in the file doc, and `253ba110b` in the speculative-decoding doc (`generate_speculative_with_draft`). They may be different references, but they could also be a stale comment. Worth checking.

**How far it reaches into entropic's source**

```
include/entropic/  (C ABI, interfaces)      no llama.cpp types found
        │
src/inference/inference_c_api.cpp           entropic_create_inference_backend → new LlamaCppBackend
        │                                   entropic_inference_log_silence → ggml log silencing
        ▼
LlamaCppBackend : entropic::InferenceBackend   (llama_cpp_backend.{h,cpp}, 15% layer)
   owns llama_model*, llama_context*, llama_vocab*, mtmd ctx
   uses llama_model_load_from_file, llama_init_from_model, llama_decode,
        llama_state_seq_get/set_data, llama_set_adapters_lora,
        common_chat render/parse, common_speculative_*
   ├─ LlamaCppSampler / LlamaCppSamplerFactory   (llama_sampler chain)
   ├─ LlamaCppTokenizer                          (llama_tokenize, llama_token_to_piece)
   ├─ adapter_manager.cpp                        (apply_adapter → llama_set_adapters_lora)
   └─ speculative_compat.cpp                     (llama_vocab_type comparison)
```

- **Deepest layer:** the backend uses llama.cpp's C API and also its `common/` helpers (chat-template render/parse, speculative decoding). The gh#87 notes say the PEG chat parser is vendored.
- **Leaks upward:**
  - The orchestrator `dynamic_cast`s to `LlamaCppBackend` to call `generate_speculative_with_draft`, so it knows the concrete type.
  - `llama_model_ptr()` is public and has a caller, `resolve_target_model`, which I did not open. That hands a raw llama.cpp pointer to engine code.
- **Test layer:** unit tests define link-time mocks of llama.cpp symbols (`llama_adapter_lora_init`, `llama_vocab_*`, and others), so the test build substitutes for the real library.

**Gaps:** the index cannot see the CMake/submodule wiring, and I did not check whether any header under `include/` includes llama.cpp headers. My evidence there is name-only: no llama.cpp types surfaced in `include/`.