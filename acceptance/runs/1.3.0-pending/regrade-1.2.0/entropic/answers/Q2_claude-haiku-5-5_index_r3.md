**How it's brought in:** llama.cpp is a git submodule, not a FetchContent dependency. `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`, and the superproject pins it to commit `20a04b22`. `extern/CMakeLists.txt` then builds it with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, with `LLAMA_BUILD_COMMON=ON` and `LLAMA_BUILD_TOOLS=OFF`. It also adds `llama.cpp/tools/mtmd` separately for multimodal support. Everything else in `extern/` (spdlog, ryml, Catch2, json, httplib) comes in through FetchContent. The CUDA setting is bridged to `GGML_CUDA`.

**How far it reaches:** it reaches into the engine's inference and facade layers, but the public headers mostly keep it out.

- **Includes, `src/inference/` only:** `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, `tool_call_markers.h`. The backend also pulls in `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h` and `mtmd-helper.h`.
- **Facade:** `src/facade/entropic.cpp` includes `llama_cpp_backend.h` and calls `llama_model_ptr()` and `llama_context_ptr()` on the backend for adapter load, unload and swap.
- **Public headers:** `include/` never includes llama headers. It only forward-declares `struct llama_model`, `llama_context` and `llama_adapter_lora` in `orchestrator.h`, `adapter_manager.h`, `speculative_compat.h`, and uses those raw pointers in signatures. `i_inference_backend.h` and `config.h` mention llama only in comments or identifiers. `entropic.h` does not expose llama types.

**Linking:** `entropic-inference-*` links `llama-common` publicly and `llama` and `mtmd` privately. `entropic-facade` absorbs `llama`, `mtmd` and `llama-common` as static `LINK_ONLY` dependencies into `librentropic.so`. Consumers never link llama directly, which matches the design rule that no C++ or third-party ABI crosses the `.so` boundary.

**Things to know:**
- In this checkout `extern/llama.cpp` is an empty directory: the submodule is registered but not initialized. A configure will fail until `git submodule update --init extern/llama.cpp` is run.
- The comments disagree on the pin. `llama_cpp_backend.cpp` and `extern/CMakeLists.txt` say "pinned at b8420", while the gitlink is `20a04b22`. Treat the comments as stale unless the tag is confirmed.
- The public-header forward declarations are a mild leak of the "no third-party headers in interface contracts" rule. They don't require the llama headers, but they do name llama types in the public API.