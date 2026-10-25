**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, pulled into the build by `add_subdirectory`. It reaches deep into `src/inference/` and the facade, and its types leak through a few public headers as opaque pointers. The C ABI in `entropic.h` and the backend interface are clean.

**How it's brought in**

- `.gitmodules` registers `extern/llama.cpp` pinned to commit `20a04b22`. The index shows it as a gitlink.
- `extern/CMakeLists.txt` sets llama.cpp's options (`LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` OFF, `LLAMA_BUILD_COMMON` ON), then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal. Everything else in that file (spdlog, ryml, Catch2, json, httplib) comes from `FetchContent`.
- The comment there ("llama.cpp is a submodule but NOT built in v1.8.0") is stale. The subdirectory is built now.
- Linking: `src/inference/CMakeLists.txt` links `llama`, `mtmd` (PRIVATE) and `llama-common` (PUBLIC) into the inference object library. `src/facade/CMakeLists.txt` absorbs `llama`, `mtmd` and `llama-common` into `librentropic.so` as `LINK_ONLY`, so consumers never link llama directly.
- In this checkout `extern/llama.cpp/` is empty (the submodule is not initialised). A build needs `git submodule update --init extern/llama.cpp` first. I did not build anything.

**How far it reaches into entropic's source**

1. **Wrapper layer (`src/inference/`)**, the bulk of it:
   - `llama_cpp_backend.{h,cpp}`: `LlamaCppBackend` is the concrete llama.cpp backend. It includes `llama.h`, `common.h`, `chat.h`, `sampling.h`, `speculative.h` and `mtmd*.h`, and owns `llama_model*`, `llama_context*`, the vocab and the mtmd context.
   - `llama_cpp_sampler.*`, `llama_cpp_tokenizer.*`: adapters over `llama_sampler` and `llama_vocab`.
   - `orchestrator.cpp`, `adapter_manager.cpp`, `speculative_compat.cpp`, `grammar_registry.cpp`, `inference_c_api.cpp`, `interface_factory.cpp`, `secondary_model_loader.cpp`: each includes llama headers or calls the backend directly.
   - `tool_call_markers.h` includes `chat.h` for `common_chat_format`.
   - `adapters/*` (Qwen, nemotron3) build on the chat parsing that comes from `common`.

2. **Facade**: `src/facade/entropic.cpp` includes `llama_cpp_backend.h`. The facade is where the `.so` boundary is, so the llama code is absorbed there.

3. **Public headers** (`include/entropic/`): these forward-declare `struct llama_model; struct llama_context; struct llama_adapter_lora; struct llama_vocab` and take or return those pointers:
   - `inference/adapter_manager.h`: `load`/`activate`/`swap` take `llama_context*` and `llama_model*`.
   - `inference/orchestrator.h`: `deactivate_if_active(llama_context*)`, `resolve_speculative_pair(llama_model*&, llama_model*&)`.
   - `inference/speculative_compat.h`: takes `const llama_model*`.
   - `inference/sampler.h` and `grammar_registry.h`: mention `llama_context`/`llama_sampler` in their contracts.

   These are opaque forward declarations, so no llama header is needed by consumers. Still, they are the one place llama types cross into the public surface, which conflicts with the "no third-party headers in interface contracts" rule in the architecture doc.

4. **Not reached**:
   - `include/entropic/entropic.h`: llama.cpp appears only in comments.
   - `interfaces/i_inference_backend.h`: only doc comments.
   - `core/response_generator.cpp`: no llama includes.
   - Config types: `llama_log_path` is just a path string.

5. **Tests**: many unit and model tests include `<llama.h>` or mock `llama_*` symbols at link time (e.g. `speculative_compat_test.cpp`, `adapter_manager_test.cpp`).

So the dependency is compiled and linked into the engine, has a thick wrapper in `src/inference/`, and has a few opaque-pointer leaks into `include/entropic/inference/`. It does not reach the C API or the interface contracts.