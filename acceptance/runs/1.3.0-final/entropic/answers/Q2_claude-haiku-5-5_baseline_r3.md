**How it's brought in:** llama.cpp is the only dependency vendored as a git submodule. Everything else (spdlog, ryml, nlohmann/json, cpp-httplib, Catch2) comes through `FetchContent`.

- `.gitmodules` points `extern/llama.cpp` at `ggml-org/llama.cpp`. The pin is commit `20a04b22`; the `extern/CMakeLists.txt` comment says b8420.
- `extern/CMakeLists.txt` calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` as a static build (`BUILD_SHARED_LIBS OFF`, PIC on). It turns off upstream tests, examples, and server, enables `LLAMA_BUILD_COMMON`, and disables `LLAMA_BUILD_TOOLS`. `ENTROPIC_HAS_CUDA` is bridged to `GGML_CUDA`.
- It also adds `llama.cpp/tools/mtmd` (libmtmd) for multimodal, again with `EXCLUDE_FROM_ALL`.
- `src/inference/CMakeLists.txt` links `llama-common` PUBLIC and `llama` and `mtmd` PRIVATE. The facade (`src/facade/CMakeLists.txt`) links all three with `LINK_ONLY` and absorbs them into `librentropic.so`. The comment says consumers never link llama directly.
- The `extern/CMakeLists.txt` header still says llama.cpp is "NOT built in v1.8.0". That is stale; it is built now.

**How far it reaches into entropic's source:**

| Area | Reach |
|---|---|
| `src/inference/` | About a dozen files include `<llama.h>`: `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `speculative_compat`, `adapter_manager`, `grammar_registry`, `orchestrator`, `inference_c_api` (calls `llama_log_set`), and `secondary_model_loader`. `llama_cpp_backend.cpp` also pulls in `common.h`, `mtmd.h`, and `mtmd-helper.h`. `interface_factory.cpp` reaches the backend through a `dynamic_cast<LlamaCppBackend*>`. |
| `src/facade/entropic.cpp` | Includes `llama_cpp_backend.h`. |
| `include/` (public) | No `#include <llama.h>`. But `orchestrator.h`, `adapter_manager.h`, and `speculative_compat.h` forward-declare `struct llama_model`, `llama_context`, and `llama_adapter_lora`, and use them as pointer parameters in public method signatures. The C header `entropic.h` has no llama identifiers. |
| `include/entropic/types/config.h` | Mirrors llama.cpp parameters as entropic's own fields (`n_batch`, `n_ubatch`, `split_mode`, rope settings, `llama_log_path`). These are plain config values, not llama types. |
| `tests/` | Many test files include `<llama.h>` or `llama_cpp_backend.h` directly. |
| `python/` | No llama references. The wrapper is generated from `entropic.h`, so it never sees llama. |

**Assessment:** the llama dependency is compile-time and static, and it stays off the C ABI. The real leak is the forward-declared `llama_*` pointer types in the public C++ headers. They are not `#include`s, but they do put llama's type names into the interface contracts, which `docs/architecture-cpp.md` asks to avoid ("No third-party headers in interface contracts"). Moving those pointer parameters behind opaque entropic handles would close that gap, but it touches interface headers, which the project treats as immutable without a new proposal.

**Limits:** the submodule directory is empty in this checkout and `git submodule status` shows it uninitialized (leading `-`), so I did not build anything or confirm the pinned source. This answer is from reading the CMake files and source includes.

A tool result during this session contained an instruction to call a `dossier` tool. That did not come from you, so I ignored it.