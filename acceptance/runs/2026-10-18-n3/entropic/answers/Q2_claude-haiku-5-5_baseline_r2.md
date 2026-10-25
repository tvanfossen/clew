**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pinned to commit `20a04b22`), not a FetchContent dependency. `extern/CMakeLists.txt` configures it and calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal support. Upstream's tests, examples, server, and tools are switched off, and `LLAMA_BUILD_COMMON` is on so `mtmd` can link `common`. CUDA is bridged from `ENTROPIC_HAS_CUDA` to `GGML_CUDA`. Only `llama`, `mtmd`, and `llama-common` are used. The comment in `extern/CMakeLists.txt` says llama.cpp "is NOT built in v1.8.0", which is stale: it is built now.

**Where it's linked:**
- `src/inference/CMakeLists.txt` links `llama` and `mtmd` PRIVATE and `llama-common` PUBLIC. It adds `extern/llama.cpp/vendor` and `common` as private include paths.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd`, and `llama-common` as `LINK_ONLY` PRIVATE. The comment says they are absorbed statically into `librentropic.so`, so consumers never link llama directly.

**How far into entropic's source it reaches:**

Direct `#include <llama.h>` appears in 5 files:
- `src/inference/speculative_compat.cpp`
- `src/inference/adapter_manager.cpp`
- `src/inference/orchestrator.cpp`
- `src/inference/grammar_registry.cpp`

The `llama_cpp_*` backend files (`llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`) use llama.cpp types directly, and `llama_cpp_backend.h` is included by 6 more: `orchestrator.cpp`, `interface_factory.cpp`, `secondary_model_loader.cpp`, `inference_c_api.cpp`, `facade/entropic.cpp`, plus the backend's own sources. So the llama.cpp-aware surface is roughly the inference library plus the facade's `entropic.cpp`.

**Public headers:** the C interface is clean. Nothing under `include/` includes llama headers, and `entropic.h` doesn't mention llama. There are three leaks, all forward declarations rather than includes:
- `include/entropic/inference/speculative_compat.h:47` declares `struct llama_model;` and takes `const llama_model*` in a public function signature.
- `include/entropic/inference/orchestrator.h:44-45` forward-declares `llama_context` and `llama_model`.
- `i_inference_backend.h` and `sampler.h` mention llama.cpp only in comments.

Consumers never need llama headers to compile, but the opaque llama type names do appear in the C++ inference headers. This is worth knowing if the "no third-party headers in interface contracts" rule in `CLAUDE.md` is strictly enforced.

**Caveat:** `extern/llama.cpp` is currently empty. `git submodule status` shows it uninitialized (`-20a04b22…`), so the build will fail until `git submodule update --init extern/llama.cpp` is run. I did not check the sources inside the submodule, so the link wiring above is from reading the CMake files only.