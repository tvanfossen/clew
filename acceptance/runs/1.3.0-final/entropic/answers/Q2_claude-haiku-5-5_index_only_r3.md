**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, built into the inference library and not into the top-level engine. Only the `src/inference/` layer calls its C API, and nothing in the public `include/entropic/` interface exposes its types.

**How it's brought in**

- `extern/CMakeLists.txt` says llama.cpp is a submodule and is not built by that file. Other external dependencies are fetched at configure time with FetchContent. The doc comment still says "not built in v1.8.0", which looks stale, since the release notes describe a later pin bump.
- `src/inference/CMakeLists.txt` says the inference library links against llama.cpp, nlohmann/json and spdlog. The per-backend library `librentropic-inference-{cuda,vulkan,cpu}.so` is the artifact that links `llama.cpp`, per `docs/architecture-cpp.md`. So the variant is chosen at compile time.
- The pinned version is inconsistent across docs. `llama_cpp_backend.cpp` says "pinned against llama.cpp submodule b8420". `RELEASE_NOTES.md` records a bump to b9592 (`extern/llama.cpp` 253ba110b → ac4cddeb) in v2.9.0. I'd trust the release notes, but the index can't confirm which commit the submodule currently points to.

**How far it reaches into entropic's source**

- **Contained in one module.** Direct llama.cpp usage lives in `src/inference/`: `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.{h,cpp}`, `llama_cpp_tokenizer.{h,cpp}`, plus `adapter_manager.cpp` (LoRA) and `image_preprocessor.cpp` (uses the stb_image vendored with llama.cpp). Those files hold the bulk of the 134 symbols in `LlamaCppBackend`, which are the decode loop, prefill, KV-cache prefix reuse, batching, speculative and MTP decode, multimodal, and the chat-template paths.
- **Adapters, not the core.** `LlamaCppBackend` is a 15% "common patterns" layer. Its header describes a versioned subclass pattern, with a pinned-commit subclass (`LlamaCppBackend_b8420`) meant to hold the version-specific API calls. `LlamaCppSampler` wraps a `llama_sampler*` chain. `LlamaCppTokenizer` wraps a borrowed `llama_vocab*`.
- **Public surface.** Some llama.cpp types leak through accessors on the backend class, such as `llama_model_ptr()` and `llama_context_ptr()`. The index does not show whether any of these reach `include/entropic/`. The `llama_log_path` config entry is a string, not a llama type.
- **Tests.** Unit tests mock the llama.cpp adapter functions by link-time substitution (`tests/unit/inference/adapter_manager_test.cpp`), so the CPU-only gate doesn't need the real library.
- **Not visible.** The index holds only one llama.cpp file, a stub `llama.h` with no symbols and no documentation. The `extern/` tree is not indexed, so I can't see llama.cpp's own API or confirm which functions entropic calls beyond what its own bodies name.

**What I could not establish from the index:** whether any `include/entropic/*.h` header exposes llama.cpp types, the exact submodule commit, and how the Python wrapper's `entropic.h` consumption interacts with llama.cpp. Checking the CMake files directly and the `include/entropic/` headers would settle those.