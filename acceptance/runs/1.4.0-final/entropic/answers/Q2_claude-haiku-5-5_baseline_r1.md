**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, pinned to b8420 (later bumped to `20a04b22`, per the decision log), and CMake builds it in-tree with `add_subdirectory`. Its code reaches the inference backend, tokenizer, sampler, speculative, adapter, grammar, and multimodal paths in `src/`, plus the facade and tests. The public `include/` headers mention llama types only as opaque forward declarations, so consumers never see llama.h.

**How it is brought in**

- `.gitmodules` declares `extern/llama.cpp` from `ggml-org/llama.cpp`.
- `extern/CMakeLists.txt` configures it. It is not a FetchContent dependency like spdlog, ryml, json, or httplib. It sets `LLAMA_BUILD_COMMON=ON`, `LLAMA_BUILD_TOOLS/EXAMPLES/SERVER/TESTS=OFF`, and `GGML_CUDA` from `ENTROPIC_HAS_CUDA`. It then runs `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` and separately `add_subdirectory(llama.cpp/tools/mtmd ...)` for multimodal.
- The root `CMakeLists.txt` pulls in `extern/` before the `src/` subdirectories.
- Static libs `llama`, `llama-common`, and `mtmd` are linked `$<LINK_ONLY:>` into `entropic-facade`, so they are absorbed into `librentropic.so`. Consumers link only the facade.

**How far it reaches into entropic's source**

- **Direct includes:** 12 files under `src/` and `tests/` include `<llama.h>`, `<common.h>`, `<chat.h>`, `<sampling.h>`, `<speculative.h>`, `<mtmd.h>`, or `<mtmd-helper.h>`. The heaviest users are `llama_cpp_backend.{h,cpp}`, `orchestrator.cpp`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, and `tool_call_markers.h`. Outside `src/inference/`, only `src/facade/entropic.cpp` (via `llama_cpp_backend.h`) touches it.
- **Public headers:** `include/` contains no `#include` of llama. It has opaque forward declarations `struct llama_model;` and `struct llama_context;` in `include/entropic/inference/orchestrator.h` and `speculative_compat.h`, plus pointer-typed signatures using them. The rest of the llama mentions in `include/` are comments or config field docs. That matches design rule 1 (pure C ABI, opaque handles).
- **Python:** `python/` has no direct llama reference. The wrapper is generated from `entropic.h`.
- **Docs and tasks:** `tasks.py` and `docs/architecture-cpp.md` describe the pin and absorbed-library model but do not drive the build.

**Things to know**

- The submodule is **empty in this checkout**. `extern/llama.cpp` exists but contains nothing, and `git submodule status` shows it uninitialized (`-20a04b...`). Configuring this tree as-is fails at `add_subdirectory(llama.cpp)`. It needs `git submodule update --init extern/llama.cpp` first. I did not run a configure or build, so I have not verified that failure mode, only inferred it from the empty directory.
- `extern/CMakeLists.txt` has a stale header comment saying llama.cpp "is NOT built in v1.8.0". The code below it builds it.
- `llama-common` is linked PUBLIC into the inference OBJECT library, which exposes common.h, chat.h, and related headers to the facade target. The facade's own consumer-facing link is LINK_ONLY, so this does not leak out of the shared library.