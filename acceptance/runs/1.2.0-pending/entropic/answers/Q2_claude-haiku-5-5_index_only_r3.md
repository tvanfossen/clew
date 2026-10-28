**Short answer:** llama.cpp is vendored as a git submodule and linked into the inference library. Its reach into entropic's source is confined to the `src/inference/llama_cpp_*` files, plus test mocks. The public C headers under `include/entropic/` don't expose it. I answered from the index only, so I could not read the CMake bodies or the submodule itself.

**How it's brought in**

- **Submodule:** `src/inference/llama_cpp_backend.cpp` is documented as "Pinned against llama.cpp submodule b8420."
- **CMake wiring:** `src/inference/CMakeLists.txt` says the inference library "Links against llama.cpp, nlohmann/json, and spdlog." I could not see the link lines, so I can't say whether it uses `add_subdirectory` or `target_link_libraries` on a submodule target.
- **Stale comment:** `extern/CMakeLists.txt` says external deps are fetched via `FetchContent`, and that "llama.cpp is a submodule but NOT built in v1.8.0." That comment predates the current v2.9.20 tree and is probably out of date, so don't rely on it for the current build mode.

**How far it reaches**

- **Inside the llama.cpp layer:** `LlamaCppBackend` (`src/inference/llama_cpp_backend.{h,cpp}`) uses the llama.cpp C API directly (`llama_model_load_from_file`, `llama_init_from_model`, `llama_decode`, `llama_chat_apply_template`, and related calls). It also has multi-sequence batching, speculative and MTP decoding, multimodal (mtmd), and LoRA adapter support. Its header says it is "Internal to inference .so."
- **Adapters:** `LlamaCppSampler` / `LlamaCppSamplerFactory` wrap `llama_sampler` chains. `LlamaCppTokenizer` wraps `llama_vocab`. Both borrow pointers owned by the model or context, and the header comments state the destruction order that the backend must enforce.
- **Outside the layer:** The public surface reports no llama.cpp types. The `llama`-matching names I could see in `include/` were limited to `llama_log_path`, a config variable. My search was capped at 50 rows, so I can't rule out other hits. The rest of the matches were in `src/` and `tests/`.
- **Tests:** `tests/unit/inference/` mocks llama.cpp functions at link time (for example `llama_adapter_lora_init`, `llama_model_get_vocab`, and `llama_vocab_*`), so unit tests don't need the real library.

**Gaps:** The index can't show the CMake link lines, the submodule's contents, or whether `llama.h` at the repo root is the vendored header or something else. It also doesn't cover CI. Reading `src/inference/CMakeLists.txt`, the top-level `CMakeLists.txt`, and `.gitmodules` would settle the build mechanism.