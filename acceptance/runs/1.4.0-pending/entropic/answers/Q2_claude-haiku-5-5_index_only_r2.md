**Short answer:** llama.cpp comes in as a git submodule, and it is linked by the inference library rather than built by the top-level build. Its API reaches into entropic's source only through a small `src/inference/llama_cpp_*` adapter layer. The public headers and the rest of the engine see only entropic's own abstractions.

**How it's brought in (what the index shows):**

- **Submodule:** `src/inference/llama_cpp_backend.cpp` is documented as "Pinned against llama.cpp submodule b8420", and `speculative_compat.cpp` refers to `extern/llama.cpp/common/speculative.cpp`. The index does not hold the submodule's own files.
- **Link:** `src/inference/CMakeLists.txt` is described as "Links against llama.cpp, nlohmann/json, and spdlog."
- **Stale comment:** `extern/CMakeLists.txt` says llama.cpp "is a submodule but NOT built in v1.8.0" and describes FetchContent for header-only libraries. That comment predates the current engine. I could not read the CMake logic through the index, so I can't confirm the exact mechanism from it.
- **Pin mismatch:** the file header says b8420, and the speculative-decoding notes say pin `253ba110b`. Those may be different pins, or one may be stale. Check the submodule SHA.

**How far it reaches into entropic's source:**

| Layer | llama.cpp reach |
|---|---|
| `src/inference/llama_cpp_backend.{h,cpp}` | Deep. `LlamaCppBackend` owns `llama_model*`, `llama_context*` and `mtmd` handles. It calls the C API directly (`llama_model_load_from_file`, decode, KV seq ops, state save/restore) and uses the `common_chat` and `common_speculative` helpers. It also holds the speculative, MTP and batched decode loops. |
| `src/inference/llama_cpp_sampler.{h,cpp}` | Wraps a `llama_sampler` chain. Implements the `Sampler` / `SamplerFactory` seam. |
| `src/inference/llama_cpp_tokenizer.{h,cpp}` | Wraps a borrowed `llama_vocab*`. Implements the `Tokenizer` seam. |
| `src/inference/adapter_manager.cpp`, `speculative_compat.cpp`, `prompt_cache.h`, `tool_call_markers.h`, `image_preprocessor.cpp` | Use llama.cpp LoRA, vocab, state, chat-format and `stb_image` calls directly. |
| `include/entropic/interfaces/i_inference_backend.h`, `include/entropic/inference/{sampler,tokenizer}.h` | Abstract seams with no llama.cpp types. The public `entropic_inference_log_*` C functions are documented as silencing llama/ggml logs. |
| `include/entropic/types/config.h` | Config fields that name llama.cpp concepts, such as `frequency_penalty`, `presence_penalty` and `ggml_logging`. These are config names, not llama.cpp types. |
| Tests under `tests/unit/inference` and `tests/model` | Mock the `llama_*` functions at link time, or load real or vocab-only GGUFs. |

Other engine code, such as the orchestrator and agent loop, reaches llama.cpp only through `InferenceBackend`. One caveat: the orchestrator's `resolve_target_model` and `resolve_speculative_pair` return raw `llama_model*` pointers, so a few non-adapter symbols do see llama types.

**Limits of this answer:** the index does not hold llama.cpp's own sources, and I could not read the CMake files, so the build wiring is inferred from doc comments. The symbol list was capped at 200 results. I'm not aware of anything beyond the 200, but I can't rule it out from this index.