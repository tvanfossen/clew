**How it's brought in:** The index can't show the build wiring directly. It does show three things:

- `extern/CMakeLists.txt` is the only indexed file under `extern/`, which suggests the vendored llama.cpp is pulled in through CMake. The index holds no symbols from it, and its contents are not parsed, so I couldn't read how it's wired.
- The file doc for `src/inference/llama_cpp_backend.cpp` says it is "Pinned against llama.cpp submodule b8420", so the dependency is a git submodule at a fixed commit.
- A config search for "llama" returned nothing, so the index has no config-level entry for it.

**How far it reaches into entropic's source:** Llama.cpp types and calls appear across the inference layer, but only there.

- **Core backend:** `LlamaCppBackend` (`src/inference/llama_cpp_backend.h`/`.cpp`) is the main integration point. It derives from `entropic::InferenceBackend` and holds raw `llama_model*`, `llama_context*` and `llama_vocab*` members. Its public header exposes `llama_model_ptr()` and `llama_context_ptr()`, which return llama.cpp types directly. It also has llama-specific public methods for common-chat parsing, speculative decoding (including an MTP head) and sequence-state save/restore.
- **Adapters:** `LlamaCppSampler` and `LlamaCppSamplerFactory` (`src/inference/llama_cpp_sampler.h`/`.cpp`) wrap the `llama_sampler` chain. `LlamaCppTokenizer` (`src/inference/llama_cpp_tokenizer.h`/`.cpp`) wraps `llama_tokenize` and the vocab API.
- **Helpers:** `adapter_manager.cpp` (LoRA via `llama_set_adapters_lora`), `speculative_compat.cpp` (vocab-type checks) and `to_llama_chat` and the param builders in `llama_cpp_backend.cpp`.
- **Public surface:** `include/entropic/interfaces/i_inference_backend.h` declares `entropic_inference_log_silence` and `entropic_inference_log_to_file`, which are about llama/ggml logging. `include/entropic/types/config.h` has `llama_log_path`. The index doesn't show whether any llama.cpp type leaks into the interface headers. That is the rule to check, since the design doc says no third-party headers in interface contracts and `llama_model_ptr()` is a visible exception.
- **Tests:** several unit tests define mock `llama_*` functions at link time (`adapter_manager_test.cpp`, `speculative_compat_test.cpp`, `vocab_only_smoke_test.cpp`), so the unit tests run against stubs rather than the real library.

**Not reached:** The search shows no llama.cpp symbols in the engine's orchestration, session or Python layers. The Python wrapper is generated from `entropic.h`, which the index does not list as containing llama types.

**To settle the open points:** read `extern/CMakeLists.txt` and the top-level CMake for the submodule and link setup, and grep the `include/entropic/` headers for `llama` includes. Both are outside what this index covers.