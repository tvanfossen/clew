**How it's brought in**

llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pinned to commit `20a04b22`; the comments say b8420, and `docs/architecture-cpp.md` cites `253ba110b` for some behaviour, so the pin comments disagree). `extern/CMakeLists.txt` pulls it in with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` after forcing `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` off and `LLAMA_BUILD_COMMON` on. It then adds only `llama.cpp/tools/mtmd` for multimodal, again `EXCLUDE_FROM_ALL`. The only other dependencies (spdlog, ryml, json, httplib, Catch2) come from FetchContent; llama.cpp is the one that doesn't.

`src/inference/CMakeLists.txt` builds an OBJECT library (`entropic-inference-{cpu,cuda,vulkan}`). It links `llama-common` as PUBLIC and `llama` and `mtmd` as PRIVATE. `src/facade/CMakeLists.txt` then absorbs `llama`, `mtmd` and `llama-common` into `librentropic.so` as `LINK_ONLY` dependencies, so consumers don't link llama directly.

One thing to check: `git submodule status` shows `-20a04b22…` (uninitialised), and `extern/llama.cpp` is empty in this checkout. Configuring will fail until `git submodule update --init extern/llama.cpp` is run.

**How far it reaches into entropic's source**

- **Contained in `src/inference/`.** About 190 `llama_*` call sites live there, in `llama_cpp_backend`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `adapter_manager`, `orchestrator`, `grammar_registry`, `speculative_compat`, `inference_c_api`, `prompt_cache`, `tool_call_markers.h` and the adapters. `llama_cpp_*` is the only place that includes `llama.h` or the `common/` headers.
- **`src/facade/entropic.cpp`** is the one outside consumer. It includes `llama_cpp_backend.h` and calls `llama_model_ptr()` and `llama_context_ptr()` to wire the adapter manager. Its include path also points at `extern/llama.cpp/include` and `ggml/include`.
- **`src/core`, `src/mcp`, `src/config`, `src/storage`, `src/cli`** contain no llama references.
- **Public headers leak the types, but only as forward declarations.** `include/entropic/inference/orchestrator.h` takes `llama_context*` and `llama_model*` in method signatures, and `speculative_compat.h` takes `const llama_model*`. `sampler.h` and `i_inference_backend.h` mention llama only in comments or docs. No public header includes `llama.h`. This goes against the architecture rule "no third-party headers in interface contracts": the rule holds for includes but not for the signatures.

In short: the dependency is a pinned, statically absorbed submodule. Its C types reach the public API through `orchestrator.h` and `speculative_compat.h`, and the facade touches it only to pass model and context pointers to the adapter manager. Everything else stays in `src/inference/`.