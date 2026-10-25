**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, upstream `ggml-org/llama.cpp`). It is built from source, not fetched. `extern/CMakeLists.txt` calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` with `BUILD_SHARED_LIBS` forced OFF, so it becomes a static library. It also adds `llama.cpp/tools/mtmd` by hand for multimodal support. `LLAMA_BUILD_COMMON` is ON so `common` exists for the speculative and sampler code. Examples, server and tools are OFF. CUDA is wired through `ENTROPIC_HAS_CUDA` → `GGML_CUDA`. Everything else in that file (spdlog, Catch2, ryml, json, httplib) uses FetchContent. llama.cpp is the only dependency that is vendored as a submodule.

**How it is linked:**
- `src/inference/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` into the inference objects.
- `src/facade/CMakeLists.txt` links the same three as `$<LINK_ONLY:>` PRIVATE, so they are absorbed into `librentropic.so`. Consumers never link llama.cpp directly.

**How far it reaches into entropic's source:**

| Layer | llama.cpp exposure |
|---|---|
| `src/inference/llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.*`, `llama_cpp_tokenizer.*` | Full. These are the adapters that wrap the C API. The backend header includes `llama.h`. |
| Other `src/inference/` files | Direct includes of `llama.h` in `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp` and `speculative_compat.cpp`. `llama_cpp_backend.cpp` also includes `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h` and `mtmd-helper.h`. `tool_call_markers.h` includes `chat.h`. `inference_c_api.cpp` pulls `llama.h` in through the backend header. |
| `src/facade/entropic.cpp` | Uses `LlamaCppBackend` via `dynamic_cast` to get `llama_model_ptr()` and `llama_context_ptr()` for the LoRA adapter calls. It does not include `llama.h` itself. |
| `src/config/loader.cpp`, `ModelConfig` | Llama knobs such as `llama_log_path` and cache types are parsed as config. These are entropic's own types, not llama.cpp types. |
| Public `include/entropic/` | No `#include` of any llama.cpp header. There are forward declarations only: `struct llama_model;` and `struct llama_context;` appear in `inference/orchestrator.h`. `speculative_compat.h` declares a function taking `const llama_model*`. |
| C ABI `entropic.h` | No llama.cpp types. |
| Tests | Several test files include `llama.h` and `chat.h` directly. |

**Summary:** The dependency is a static, submodule-built llama.cpp that is confined to `src/inference/`. It leaks outward in two places. The facade's LoRA path reaches the backend's raw `llama_model*`/`llama_context*` pointers. Public C++ headers forward-declare llama structs and accept them as parameters. The C ABI stays clean.

**Stale comments noticed:**
- `extern/CMakeLists.txt` still says llama.cpp "is NOT built in v1.8.0", but it is built now.
- The pin is described as `b8420` in one place and `253ba110b` in another.

I did not run a build, so the link behaviour above comes from reading the CMake files.