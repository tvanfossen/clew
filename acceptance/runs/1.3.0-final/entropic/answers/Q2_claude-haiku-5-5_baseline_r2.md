**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, built from source into `librentropic.so` via `add_subdirectory`. It reaches into entropic's source through the inference layer (`src/inference/`) and a few facade and adapter call sites. The public `include/entropic/` headers mostly keep it out, but forward-declare its types in a few places.

**How it's brought in**

- `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. The commit comment in `extern/CMakeLists.txt` says it is pinned at b8420.
- `extern/CMakeLists.txt` sets the llama build options (`LLAMA_BUILD_TESTS/EXAMPLES/SERVER OFF`, `LLAMA_BUILD_COMMON ON`, `LLAMA_BUILD_TOOLS OFF`). It maps `ENTROPIC_HAS_CUDA` to `GGML_CUDA`. It then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, and a second `add_subdirectory` for `llama.cpp/tools/mtmd` for multimodal support.
- Every other dependency (spdlog, ryml, Catch2, nlohmann/json, cpp-httplib) comes from `FetchContent`. llama.cpp is the only one that is a submodule and built as a subdirectory.
- `src/inference/CMakeLists.txt` links `llama-common` as PUBLIC and `llama` and `mtmd` as PRIVATE.
- `src/facade/CMakeLists.txt` absorbs `llama`, `mtmd` and `llama-common` into `entropic-facade` as `LINK_ONLY`, so consumers never link llama directly.

**How far it reaches into entropic's source**

1. **Inside `src/inference/` (deep).** Most of the llama.cpp surface is here: `llama_cpp_backend.{h,cpp}` (includes `llama.h`, `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h`), `llama_cpp_sampler`, `llama_cpp_tokenizer`, `grammar_registry`, `adapter_manager`, `speculative_compat`, `orchestrator`, `tool_call_markers.h`, and `inference_c_api.cpp`. This is the only place that uses the real llama API.
2. **Facade (shallow).** `src/facade/entropic.cpp` includes `llama_cpp_backend.h` and calls `dynamic_cast<LlamaCppBackend*>` to reach `llama_model_ptr()` and `llama_context_ptr()` for LoRA adapter load and unload. The facade's CMake also adds the llama and ggml include dirs as PRIVATE.
3. **Public headers (leaks at the type level).** `include/entropic/inference/orchestrator.h`, `adapter_manager.h` and `speculative_compat.h` forward-declare `struct llama_model`, `llama_context` and `llama_adapter_lora` and use them in signatures. Most other mentions in `include/` are comments. This conflicts with the CLAUDE.md rule "No third-party headers in interface contracts". The forward declarations are opaque, so they don't pull in llama headers, but the types are part of the public contract.
4. **Not reached:** `core/`, `config/`, `mcp/`, and the `types/` headers, apart from comments that mention llama.cpp field names.

**Things to know**

- The submodule is not checked out in this copy. `git submodule status` shows `-20a04b…` (uninitialized), and `extern/llama.cpp/tools/mtmd` is missing. The CMake will fail at configure time until `git submodule update --init` runs. I did not verify the build.
- The comment in `extern/CMakeLists.txt` says "llama.cpp is a submodule but NOT built in v1.8.0". That is stale; it is built now.