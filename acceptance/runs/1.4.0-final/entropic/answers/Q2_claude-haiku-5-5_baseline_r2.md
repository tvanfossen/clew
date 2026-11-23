**Short answer:** llama.cpp is a git submodule that CMake builds in-tree and statically absorbs into `librentropic.so`. Its headers are included directly by the C++ inference backend and a handful of helpers, but not by the C API. Only forward declarations and llama-named config fields reach the public C++ headers.

**How it's brought in**

- **Submodule:** `.gitmodules` points `extern/llama.cpp` at `ggml-org/llama.cpp`, pinned to `20a04b22`.
- **Not fetched like the others:** spdlog, ryml, Catch2, nlohmann/json and cpp-httplib come in via `FetchContent` in `extern/CMakeLists.txt`. llama.cpp is `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`.
- **Build options forced:** tests, examples and server are off. `LLAMA_BUILD_COMMON` is on, `LLAMA_BUILD_TOOLS` is off. Static, PIC, and CUDA is bridged from `ENTROPIC_HAS_CUDA`.
- **mtmd added separately:** `llama.cpp/tools/mtmd` is added as its own subdirectory for multimodal support.
- **Linkage:**
  - `src/inference/CMakeLists.txt`: the inference OBJECT library links `llama-common` PUBLIC and `llama` + `mtmd` PRIVATE.
  - `src/facade/CMakeLists.txt`: the facade absorbs `llama`, `mtmd` and `llama-common` as `LINK_ONLY` static code. Consumers never link llama directly.

**How far into entropic's source it reaches**

| Layer | Reach |
|---|---|
| `src/inference/` | Direct `#include <llama.h>`, `<common.h>`, `<chat.h>`, `<sampling.h>`, `<mtmd.h>` in `llama_cpp_backend.cpp`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, `adapter_manager.cpp`, `orchestrator.cpp`, and `tool_call_markers.h`. |
| `src/inference/llama_cpp_backend.h` | Includes `llama.h` and exposes raw `llama_model*` / `llama_context*` accessors (lines ~210, ~218). |
| `src/facade/` | Reaches llama only transitively through `llama_cpp_backend.h`, via include paths. |
| `include/entropic/` (C API, `entropic.h`) | No llama headers. Mentions are comments only. |
| `include/entropic/` (C++ headers) | No `#include` of llama headers, but forward declarations `struct llama_context;` / `struct llama_model;` in `inference/orchestrator.h:44-45` and `inference/speculative_compat.h:47`. Public methods take those pointers (`orchestrator.h:759, 773, 892`). |
| `include/entropic/types/config.h` | Config structs mirror llama.cpp parameters by name and semantics (`n_ubatch`, `split_mode`, `rope_freq_base`, `n_seq_max`, penalties). The types are plain C++, not llama types. |
| Tests | Several include `llama.h` / `chat.h` directly. |

So the header-level boundary is clean at the C ABI, and the C++ public headers only leak llama *type names* via forward declarations. That is a mild breach of the "no third-party headers in interface contracts" rule in `CLAUDE.md`, since the declarations are forward-only and need no llama header to compile.

**Caveats**

- **Submodule is empty here.** `git submodule status` shows `-20a04b22…`, meaning uninitialized, and `extern/llama.cpp/` has no contents. I could not verify llama.cpp's internal APIs or build anything. Running `git submodule update --init` is needed before this tree will configure.
- **Stale pin comments.** `extern/CMakeLists.txt` says "pinned at b8420", and `speculative_compat.h` cites commit `253ba110b`. Neither matches the current submodule pin `20a04b22`.