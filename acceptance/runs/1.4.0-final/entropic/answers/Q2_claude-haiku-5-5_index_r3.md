**How it's brought in:** a git submodule at `extern/llama.cpp`, pinned to b8420 per the comment in `extern/CMakeLists.txt`. The root build does not use `find_package` or FetchContent for it. `extern/CMakeLists.txt` sets the `LLAMA_BUILD_*` cache options (tests, examples, server, and tools all OFF, `LLAMA_BUILD_COMMON` ON), maps `ENTROPIC_HAS_CUDA` to `GGML_CUDA`, then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal. Everything is forced static (`BUILD_SHARED_LIBS OFF`) and absorbed into `librentropic.so`, so consumers never link llama directly. The `entropic-facade` target takes `llama`, `mtmd`, and `llama-common` as `LINK_ONLY` PRIVATE dependencies.

The comment at the top of `extern/CMakeLists.txt` ("NOT built in v1.8.0") is stale. The `add_subdirectory` call contradicts it.

**How far it reaches into entropic's source:**

| Layer | Reach | Evidence |
|---|---|---|
| Build / link | Wide in the inference target, narrow elsewhere | `src/inference/CMakeLists.txt` links `llama` and `mtmd` PRIVATE, and `llama-common` PUBLIC |
| `src/inference/` | Deep. About 25 files in `src/` touch llama, ggml, or common symbols, roughly 677 occurrences in total | `llama_cpp_backend.cpp` (328 hits), `orchestrator.cpp`, `llama_cpp_sampler.cpp`, `adapter_manager.cpp`, `speculative_compat.cpp`, `inference_c_api.cpp` |
| Public headers (`include/`) | No `#include` of any llama header | The only hits are forward declarations in `include/entropic/inference/adapter_manager.h` and prose or config-field comments in `entropic.h` and `types/config.h` |
| Facade (`src/facade/entropic.cpp`) | Indirect, via the concrete class | Includes `llama_cpp_backend.h` and calls `llama->llama_model_ptr()` and `llama_context_ptr()` to drive adapters |
| Core / config | Names only | `core/response_generator.cpp` and `core/engine.cpp` mention llama in comments; `config/loader.cpp` reads `ggml_logging` and `llama_log_path` config keys |

**Summary:** The dependency is compiled in statically and stays inside `src/inference/`. The public C ABI is clean at the include level, but llama.cpp's concepts leak out in three places:

1. **Config schema.** `include/entropic/types/config.h` mirrors llama.cpp knobs one-to-one (`n_ubatch`, `split_mode`, `rope_freq_base`, penalties, and so on).
2. **Adapter API.** `adapter_manager.h` takes `llama_model*` and `llama_context*`. The facade obtains those pointers from the concrete `LlamaCppBackend`.
3. **Logging.** `inference_c_api.cpp` calls `llama_log_set` directly for ggml logging.

Those leaks are by design rather than accidental, but they are the parts that would have to change if llama.cpp were swapped out.