**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pinned by gitlink `20a04b22`), not a FetchContent dependency like spdlog, ryml, nlohmann/json, httplib, or Catch2. `extern/CMakeLists.txt` configures it and then pulls it in with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal support. The config sets `LLAMA_BUILD_COMMON=ON`, `LLAMA_BUILD_TOOLS/EXAMPLES/SERVER/TESTS=OFF`, and forwards `ENTROPIC_HAS_CUDA` to `GGML_CUDA`. The comment there says the pin is "b8420", but the gitlink hash is what actually pins it, so that comment may be stale.

**Caveat for this checkout:** `extern/llama.cpp/` is empty and `git submodule status` shows it uninitialized (`-` prefix). A configure will fail until `git submodule update --init extern/llama.cpp` is run. I did not run a build.

**Link wiring:**
- `src/inference/CMakeLists.txt` links `llama-common` as PUBLIC and `llama` and `mtmd` as PRIVATE. It also adds `extern/llama.cpp/common` and `vendor` as private include paths.
- `src/facade/CMakeLists.txt` absorbs `llama`, `mtmd`, and `llama-common` statically into `librentropic.so` via `$<LINK_ONLY:>`.
- `cmake/entropic-config.cmake.in` says consumers need no llama dependency. Only system libraries reach them.

**How far it reaches into entropic's source:**

- **Deep inside `src/inference/`.** Seven files include `<llama.h>` directly: `llama_cpp_backend.h`, `llama_cpp_backend.cpp`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `speculative_compat.cpp`, `adapter_manager.cpp`, `orchestrator.cpp`, and `grammar_registry.cpp`. Several more call llama APIs through `LlamaCppBackend`. Llama calls live throughout the backend, sampler, tokenizer, speculative decoding, LoRA adapter management, grammar handling, and multimodal preprocessing.
- **Facade.** `src/facade/entropic.cpp` includes `llama_cpp_backend.h` and uses `dynamic_cast<LlamaCppBackend*>` to reach `llama_model_ptr()` for adapter loading (around line 2922).
- **Public headers: a few leaks, but not the C ABI.** `include/entropic/` never includes `<llama.h>`. It forward-declares `struct llama_model`, `llama_context`, and `llama_adapter_lora`, and exposes them as pointer parameters in `inference/orchestrator.h` (around lines 759–892) and `inference/speculative_compat.h` (line 94). The C header `entropic.h` mentions llama only in comments and error docs, and the config types mention llama.cpp pass-through fields and adapter-call names.

**Summary:** The dependency is a submodule built in-tree and absorbed statically into `librentropic.so`. Its types stay inside the C++ inference layer and appear only as opaque forward-declared pointers in a few public C++ headers. The C interface and consumers don't see it.