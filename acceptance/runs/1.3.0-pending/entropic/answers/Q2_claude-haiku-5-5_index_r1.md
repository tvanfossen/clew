**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pinned to commit `20a04b22`). It is not fetched by FetchContent, unlike spdlog, ryml, json, httplib and Catch2 in `extern/CMakeLists.txt`. The CMake wiring is in `extern/CMakeLists.txt`:

- It sets the llama.cpp options before the subdirectory is added: examples, server and tools off, `LLAMA_BUILD_COMMON` on, and `GGML_CUDA` bridged from `ENTROPIC_HAS_CUDA`.
- It builds with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, which also pulls in the `common` library. It then adds `llama.cpp/tools/mtmd` for multimodal support, again `EXCLUDE_FROM_ALL`.
- Static libraries are forced with `BUILD_SHARED_LIBS` saved and restored around the call.

Nothing from llama.cpp is installed for consumers. `librentropic.so` absorbs `llama`, `mtmd` and `llama-common` as static code through `$<LINK_ONLY:...>` in `src/facade/CMakeLists.txt`. `cmake/entropic-config.cmake.in` says consumers need no llama.cpp `find_dependency()`.

**How far it reaches into entropic's source:** the reach is wide inside the engine, but it stops at the public boundary.

- **Direct llama.cpp includes (all in `src/`):**
  - `src/inference/llama_cpp_backend.{h,cpp}`: the main user. It includes `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h` and `mtmd-helper.h`.
  - `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `grammar_registry.cpp`, `orchestrator.cpp`, `adapter_manager.cpp`, `speculative_compat.cpp`: each includes `llama.h`.
  - `tool_call_markers.h` includes `chat.h`.
- **Other `src/` consumer:** `src/facade/entropic.cpp` includes `llama_cpp_backend.h`. It `dynamic_cast`s to `LlamaCppBackend` to reach `llama_model_ptr()` and `llama_context_ptr()` for LoRA adapter load, unload and swap. That is the one place the facade looks past the backend abstraction.
- **Public headers:** `include/entropic/` has no `#include` of any llama header. It only forward-declares `struct llama_model`, `llama_context` and `llama_adapter_lora` in `inference/adapter_manager.h`, `inference/orchestrator.h` and `inference/speculative_compat.h`. Those signatures therefore expose llama pointer types. Everything else in `include/` mentions llama only in comments.
- **Outside the engine:** `src/core`, `src/config`, the CLI and the Python package contain no llama includes. `src/config/loader.cpp` reads a `llama_log_path` config key, and `include/entropic/types/config.h` has `ModelConfig` fields that map onto llama.cpp knobs such as `split_mode`. Those are config-level names, not API types.
- **Tests:** several unit tests include `llama.h` and mock its symbols at link time, for example `speculative_compat_test.cpp` and `adapter_manager_test.cpp`. The model tests include `chat.h`.

So llama.cpp is consumed as a library inside `src/inference`, with a thin leak into the facade and forward-declared pointer types in three public headers. The C API in `entropic.h` and the Python layer are clean.

```
entropic.h (C API, clean)
   └─ src/facade/entropic.cpp ──(LlamaCppBackend ptrs, LoRA ops)──┐
        └─ src/inference/*  ── llama.h / common.h / chat.h / mtmd.h
                 ▲
   include/entropic/inference/{adapter_manager,orchestrator,
   speculative_compat}.h  forward-declare llama_model/context
```

**Things I noticed but did not chase:**

- The comment in `extern/CMakeLists.txt` still says llama.cpp "is NOT built in v1.8.0", which is stale. The file actually builds it.
- Several comments reference a pinned "b8420" build, but I did not confirm that against the submodule's tag or commit.