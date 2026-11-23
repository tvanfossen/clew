The index shows llama.cpp is a git submodule under `extern/`, consumed directly through its C API, and that its use is confined to `src/inference/` plus tests. I could not read the CMake logic itself, so the build wiring is inferred from doc comments.

**How it's brought in**

- `extern/` holds llama.cpp as a git submodule. `extern/CMakeLists.txt` says external deps are fetched at configure time via FetchContent, and that llama.cpp is "a submodule but NOT built in v1.8.0". That comment is stale. Release notes describe bumping `extern/llama.cpp` to b9592, and the code is clearly built and linked now.
- `src/inference/CMakeLists.txt` says the inference library links against llama.cpp, nlohmann/json and spdlog. The root `CMakeLists.txt` and the other CMake files are indexed but have no symbols, so I could not confirm the exact target or include wiring.
- Code pins to a specific commit (the file docs say `b8420`). The index holds a `llama.h` at the repo root, but it was never harvested, so I could not inspect it.

**How far it reaches into entropic's source**

- **Inside `src/inference/`, heavily.** `llama_cpp_backend.cpp` (about 4,100 lines) calls the raw API directly: model load, context creation, `llama_decode`, batches, KV-cache sequence ops, state save/restore, chat templates, and speculative/MTP decoding. `LlamaCppBackend` exposes `llama_model_ptr()` and `llama_context_ptr()` at `src/inference/llama_cpp_backend.h:210,218`.
- **Adapter wrappers.** `llama_cpp_sampler.{h,cpp}` wraps the `llama_sampler` chain. `llama_cpp_tokenizer.{h,cpp}` wraps the vocab API. Both are thin adapters over borrowed llama pointers.
- **Other inference files.** `adapter_manager.cpp` (LoRA), `orchestrator.cpp` (model switching, `dynamic_cast` to `LlamaCppBackend`), `speculative_compat.cpp` (vocab and architecture checks), and `inference_c_api.cpp` (`llama_log_set` for silencing ggml logs) also touch llama types. `image_preprocessor.cpp` only uses stb_image vendored with llama.cpp.
- **Tests.** `tests/unit/inference/` mocks llama functions via link-time substitution, and `tests/model/` drives the real backend.
- **Public surface is clean.** Nothing under `include/entropic/` has a llama symbol in the index. The only overlap is the config field `llama_log_path` (`include/entropic/types/config.h`, parsed in `src/config/loader.cpp`), which is a plain string. The C ABI boundary therefore keeps llama types internal, which fits the design rule of no C++ or third-party types across `.so` boundaries.

**Caveat on scope.** My `llama_` code search returned 100 hits and was capped there, so the list of files above is representative, not exhaustive. The conclusion that llama types stay inside `src/inference/` rests on the public-header search, which was not capped.