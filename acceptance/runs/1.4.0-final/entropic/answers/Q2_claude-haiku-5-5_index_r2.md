**Short answer:** llama.cpp is a git submodule, built from source inside entropic's CMake tree and absorbed as static code into `librentropic.so`. Its headers are included only by the C++ inference and facade sources, never by the public `include/` headers. The one leak is that the internal `llama_cpp_backend.h` includes `llama.h` and is pulled into the facade.

**How it is brought in**

- `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. The submodule is pinned to commit `20a04b22…`. The `extern/CMakeLists.txt` comment says "pinned at b8420", but I did not check that this commit corresponds to that tag.
- `extern/CMakeLists.txt` does `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` with `LLAMA_BUILD_COMMON=ON` and `LLAMA_BUILD_TOOLS/TESTS/EXAMPLES/SERVER=OFF`. It forces `BUILD_SHARED_LIBS=OFF` and `GGML_CUDA` is bridged from `ENTROPIC_HAS_CUDA`.
- It also adds `llama.cpp/tools/mtmd` for multimodal support, with the same `EXCLUDE_FROM_ALL` treatment.
- `src/inference/CMakeLists.txt` links `llama-common` as PUBLIC and `llama` and `mtmd` as PRIVATE. The inference object library's private include paths point at `extern/llama.cpp/vendor` and `common`.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` into `entropic-facade` as `LINK_ONLY`, so they are absorbed into the shared library and do not appear in the consumer export. Its private include paths point at `extern/llama.cpp/include` and `ggml/include`.
- The CMake config template (`cmake/entropic-config.cmake.in`) lists llama.cpp among the build-time third-party deps.

**How far it reaches into entropic's source**

| Layer | Files | Reach |
|---|---|---|
| Public API (`include/entropic/`) | `inference/*.h`, `interfaces/i_inference_backend.h`, `types/*.h` | None. These only forward-declare `struct llama_model;`, `llama_context`, `llama_adapter_lora`. A grep found no `llama.h`, `ggml.h`, `mtmd.h`, `common.h` or `chat.h` include under `include/`. |
| Inference implementation (`src/inference/`) | `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.*`, `llama_cpp_tokenizer.*`, `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, `tool_call_markers.h`, `inference_c_api.cpp`, `secondary_model_loader.cpp`, `interface_factory.cpp` | Heavy. `llama_cpp_backend.cpp` includes `common.h`, `chat.h`, `mtmd.h` and `mtmd-helper.h`. `LlamaCppBackend` is the llama.cpp adapter. Sampler and tokenizer are thin wrappers over `llama_sampler` and `llama_vocab`. |
| Facade (`src/facade/entropic.cpp`) | Includes `llama_cpp_backend.h`, so `llama.h` reaches it transitively. | Indirect. |
| Core and config | `src/core/response_generator.cpp`, `src/config/loader.cpp` | Name hits only in the grep; I did not check whether they include any llama headers. |
| Tests | `tests/unit/inference/*`, `tests/model/*` | Direct use of `llama.h`, `chat.h` and mock `llama_*` functions. |

The design doc states the rule: C interfaces, no C++ ABI crossing, and no third-party headers in interface contracts. The grep results match it.

**Things to know**

- **The submodule is empty in this checkout.** `git submodule status` shows a leading `-`, and `extern/llama.cpp/` contains zero entries. A configure or build will fail until `git submodule update --init --recursive` is run. I did not build, so I have not confirmed the exact failure.
- **A stale comment.** `extern/CMakeLists.txt` says "llama.cpp is a submodule but NOT built in v1.8.0", which contradicts the later block that builds it. Only the later block is current.