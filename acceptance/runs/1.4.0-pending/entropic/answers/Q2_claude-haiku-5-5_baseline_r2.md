**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, built from source into the same shared library as the rest of entropic. Its own headers reach the inference backend, the facade and a few public headers. The core, config, MCP, storage and CLI layers never touch it.

**How it's brought in**

- `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. `git submodule status` shows it pinned at `20a04b22`.
- Unlike the other third-party deps (spdlog, ryml, Catch2, json, httplib), which use `FetchContent` at configure time, llama.cpp is built from the submodule via `add_subdirectory`.
- `extern/CMakeLists.txt` configures it: tests, examples, server and tools are off, `LLAMA_BUILD_COMMON` is on, and CUDA is bridged in via `ENTROPIC_HAS_CUDA` → `GGML_CUDA`. It is added with `EXCLUDE_FROM_ALL` and forced static (`BUILD_SHARED_LIBS OFF`) so there is no separate `libllama.so`.
- It also adds `llama.cpp/tools/mtmd` for multimodal support, again `EXCLUDE_FROM_ALL`.
- Stale comments to be aware of: the `extern/CMakeLists.txt` header says llama.cpp "is NOT built in v1.8.0", and a comment there mentions pin `b8420`. Both contradict the current code.

**Where it lands in the build**

- `src/inference/CMakeLists.txt` links the inference OBJECT library against `llama` and `mtmd` PRIVATE and `llama-common` PUBLIC. The include paths point into `extern/llama.cpp/common` and `vendor`.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` into `librentropic.so`, so they are absorbed statically. The consumer-facing `entropic-config.cmake.in` says no llama dependency is exported.

**How far it reaches into entropic's source**

| Layer | Touches llama.cpp? | Detail |
|---|---|---|
| `src/inference/` | Yes, heavily | `llama_cpp_backend.{h,cpp}` includes `llama.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h`, `mtmd-helper.h`. Also `llama_cpp_sampler`, `llama_cpp_tokenizer`, `orchestrator`, `adapter_manager`, `grammar_registry`, `speculative_compat`, `tool_call_markers.h`. |
| `src/facade/entropic.cpp` | Yes, narrowly | Includes `llama_cpp_backend.h` and `dynamic_cast`s to `LlamaCppBackend` to reach backend-specific calls. |
| `include/entropic/` (public) | Forward declarations only | `llama_model`, `llama_context`, `llama_adapter_lora` appear as opaque `struct` forward declarations in `orchestrator.h`, `adapter_manager.h` and `speculative_compat.h`, plus pointer parameters. No llama header is included and `entropic.h` (the C ABI) doesn't mention them. |
| `src/core`, `config`, `mcp`, `cli`, `storage`, `types`, `prompts` | No | Grep finds no llama includes or types there. |
| `python/` | No | Wrapper is generated from `entropic.h`. |

So the boundary is mostly clean: llama.cpp types are confined to `src/inference` and one facade file, and the public surface only exposes opaque pointers. The leak to watch is those pointer parameters in `orchestrator.h` and `adapter_manager.h`. They make the public C++ headers depend on llama's type names, even though no llama header is included.