**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pinned at `20a04b22`). It is not fetched with FetchContent, unlike spdlog, ryml, Catch2, nlohmann/json and cpp-httplib, which are declared in the same file, `extern/CMakeLists.txt`.

That file calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` and then `add_subdirectory(llama.cpp/tools/mtmd ...)`, so only the `llama`, `llama-common` and `mtmd` targets get built. It also sets `LLAMA_BUILD_TESTS`, `EXAMPLES`, `SERVER` and `TOOLS` to OFF. CUDA is bridged in by mapping `ENTROPIC_HAS_CUDA` to `GGML_CUDA`.

**How it's linked:**
- `src/inference/CMakeLists.txt` links `llama-common` PUBLIC and `llama` and `mtmd` PRIVATE into the `inference` object library.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `$<LINK_ONLY:>` PRIVATE into `librentropic.so`, so llama is absorbed statically.
- `cmake/entropic-config.cmake.in` says consumers get no llama dependency. Only system libraries reach them.

**How far into the source it reaches:**

Deep. Direct `#include <llama.h>` appears in about 15 `.cpp`/`.h` files, almost all under `src/`:

| Area | Files |
|---|---|
| Backend and kernels | `src/inference/llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer` |
| Orchestration | `orchestrator.cpp`, `adapter_manager.cpp`, `secondary_model_loader.cpp`, `speculative_compat.cpp`, `grammar_registry.cpp` |
| Wiring and facade | `interface_factory.cpp`, `src/facade/entropic.cpp` |
| C ABI | `src/inference/inference_c_api.cpp` (33 hits) |

The backend header also pulls in libmtmd's internals through forward declarations of `mtmd_context` and `mtmd_bitmap`.

**What does not leak:** the `include/` tree is mostly clean. It has no `#include` of llama or ggml headers, and `include/entropic/interfaces/i_inference_backend.h` mentions llama only in comments. Where public headers name llama types, they are opaque forward declarations:
- `include/entropic/inference/orchestrator.h` declares `struct llama_context`, `llama_model`, and uses `llama_context*` in method signatures.
- `include/entropic/inference/adapter_manager.h` declares `llama_model`, `llama_context` and `llama_adapter_lora`.
- `include/entropic/inference/sampler.h`, `tokenizer.h`, `speculative_compat.h` and `grammar_registry.h` mention llama types too.

Those declarations don't break the C ABI, but they do put llama's type names into public C++ signatures. That sits awkwardly with the stated rule of "no third-party headers in interface contracts," and is worth a decision if you want the boundary to be strict.

**Stale comments I noticed:**
- `extern/CMakeLists.txt` still says "llama.cpp is a submodule but NOT built in v1.8.0", which is no longer true.
- The submodule-pin comments disagree: one says `b8420`, another says `253ba110b`, while the checked-out SHA is `20a04b22`.

I did not build the project, so the link wiring is verified by reading the CMake files only.