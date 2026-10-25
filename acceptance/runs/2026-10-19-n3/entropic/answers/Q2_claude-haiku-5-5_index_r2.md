**How it's brought in:** llama.cpp is a git submodule, not a FetchContent dependency. `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. `extern/CMakeLists.txt` then builds it with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, which pulls in the `llama` and `ggml` targets as static code. It also adds `llama.cpp/tools/mtmd` for multimodal support, and enables `LLAMA_BUILD_COMMON` so the `llama-common` target exists. The other dependencies (spdlog, ryml, Catch2, nlohmann/json, httplib) are FetchContent. The submodule is pinned at b8420 according to the `llama_cpp_backend.cpp` header.

**Where it's linked:**
- `src/inference/CMakeLists.txt` links `llama`, `mtmd` (PRIVATE) and `llama-common` (PUBLIC) into the inference object library.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` PRIVATE dependencies. That absorbs them into `librentropic.so`, so consumers never link llama directly. The `extern/CMakeLists.txt` comments say this explicitly.

**How far it reaches into entropic's source:**

```
include/entropic/        public C headers + C++ interfaces   → forward-declares llama structs only
                                                              (no #include of llama.h)
src/inference/           llama.cpp is used directly here     → llama.h, chat.h, common.h,
  llama_cpp_backend/sampler/tokenizer                           sampling.h, speculative.h, mtmd.h
  orchestrator, adapter_manager, speculative_compat,
  grammar_registry, secondary_model_loader, inference_c_api,
  interface_factory, prompt_cache, tool_call_markers
src/facade/entropic.cpp  → includes llama_cpp_backend.h (the adapter wiring)
tests/                   → include llama.h directly in several model/unit tests
src/core, src/config     → mention llama only in comments and config keys
```

- **Confined to one layer, with a few leaks.** Only `src/inference/` and the facade include llama headers. The `include/entropic` public headers forward-declare `struct llama_model`, `llama_context` and `llama_adapter_lora` (in `orchestrator.h`, `adapter_manager.h`, `speculative_compat.h`), so llama type names appear in the public surface, but no llama header is included there.
- **Config leaks as data.** `src/config/loader.cpp` maps YAML knobs such as `llama_log_path` and the nested llama pass-through fields in `include/entropic/types/config.h` to llama.cpp parameters. This is config, not calls into llama.
- **`LlamaCppBackend` is the main seam.** The `class LlamaCppBackend` in `src/inference/llama_cpp_backend.h` derives from `InferenceBackend`. Its members expose llama types such as `llama_model_ptr()` and `llama_context_ptr()`. Callers in the inference layer, the facade and the C API use these.

**Things to note:**
- `extern/CMakeLists.txt` has a stale header comment saying llama.cpp "is a submodule but NOT built in v1.8.0". The section below it does build it (since v1.8.2), so the header comment is wrong.
- `git submodule status` shows `-20a04b2…` for `extern/llama.cpp`, which means the submodule is not initialized in this working copy. I confirmed this from the status output, not by building. A build needs `git submodule update --init extern/llama.cpp` first. The `extern/` grep only found `CMakeLists.txt`, which is consistent with that.
- I did not build the project or check the llama.cpp source, since it is not checked out here.