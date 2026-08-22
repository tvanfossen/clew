## Bringing llama.cpp in

It's a **git submodule**, not a FetchContent dependency like the project's other third-party libs (spdlog, Catch2, ryml, nlohmann/json, cpp-httplib are all `FetchContent_Declare`'d in `extern/CMakeLists.txt`). `.gitmodules` pins it:

```
[submodule "extern/llama.cpp"]
    path = extern/llama.cpp
    url  = https://github.com/ggml-org/llama.cpp.git
```

currently checked out at `20a04b22` (`gguf-v0.19.0-840-g20a04b220`). `extern/llama.cpp` is excluded from the doxygen/clew index scope as an `external_root` (1118 external files) — it's vendor code, not entropic's own source.

Build-wise, the top-level `CMakeLists.txt` does `add_subdirectory(extern)`, and `extern/CMakeLists.txt` does `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` — built as a **static lib**, PIC forced on, with `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` all OFF and `LLAMA_BUILD_COMMON ON` (needed for `common_chat_parse` etc.). It also separately pulls in `llama.cpp/tools/mtmd` for multimodal. `EXCLUDE_FROM_ALL` suppresses llama.cpp's own install rules — the comment is explicit: *"Our facade absorbs libllama.a as a static dependency; consumers never link to llama directly."* `ENTROPIC_HAS_CUDA` bridges to `GGML_CUDA` to pick the compute backend. So it's vendored source, statically linked in, version-pinned by submodule commit — not a system package, not header-only, not fetched-and-cached.

## How far it reaches into entropic's own source

It's supposed to be contained to `src/inference/`, and doxygen on `llama_cpp_backend.h` says exactly that: *"Internal to inference .so — not exposed across boundaries."* In practice the raw llama.cpp API (`<llama.h>`, `llama_model*`, `llama_context*`, `llama_log_set`, etc.) is `#include`d directly in seven files, all inside `src/inference/`:

- `llama_cpp_backend.h` / `.cpp` — the wrapper itself (decode loop, sampler chain, tokenization; a "versioned subclass" pattern with a pinned-commit subclass for API-version-specific calls)
- `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp` — sampler/tokenizer wrappers
- `grammar_registry.cpp`, `speculative_compat.cpp`, `orchestrator.cpp`, `adapter_manager.cpp` — decode-adjacent logic that needs the raw types directly rather than through the abstract interface

`interface_factory.cpp` and `inference_c_api.cpp` don't include `<llama.h>` themselves but pull it in transitively via `llama_cpp_backend.h`, and both then reach past the abstract `IInferenceBackend` interface: `interface_factory.cpp` does `dynamic_cast<LlamaCppBackend*>` to call `common_chat_parse`-backed response parsing, and `inference_c_api.cpp` calls `llama_log_set` directly to redirect llama/ggml logging.

The one place it escapes `src/inference/` entirely is **`src/facade/entropic.cpp`** — the file implementing the public `entropic.h` C API. Its `CMakeLists.txt` explicitly adds `extern/llama.cpp/include` and `extern/llama.cpp/ggml/include` to its private include path, and the `.cpp` does the same `dynamic_cast<LlamaCppBackend*>(base)` trick three times (adapter load/unload/swap) to pull out raw `llama_model*`/`llama_context*` via `llama->llama_model_ptr()`/`llama_context_ptr()` accessors, which it then hands to `adapter_manager`. So the concrete llama.cpp types leak all the way up to the facade — the outermost internal layer before the pure-C `entropic.h` boundary — though they never actually cross that C-ABI boundary itself (design rule 1: pure C only at the `.so` boundary; internal C++ dynamic-casts against a concrete backend type are the accepted escape hatch for adapter wiring, not a violation of the ABI rule, but a real breach of the "internal to inference .so" comment on `LlamaCppBackend`).
