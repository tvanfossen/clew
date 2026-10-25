**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules` points to `ggml-org/llama.cpp`, pinned in the index). It is not a FetchContent dependency like spdlog, ryml, json, or httplib. `extern/CMakeLists.txt` adds it with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, after forcing `BUILD_SHARED_LIBS OFF`, `LLAMA_BUILD_COMMON=ON`, and `LLAMA_BUILD_TOOLS/SERVER/EXAMPLES/TESTS=OFF`. It also adds `llama.cpp/tools/mtmd` for multimodal support, and maps `ENTROPIC_HAS_CUDA` to `GGML_CUDA`.

**How it links:** `src/inference/CMakeLists.txt` links `llama-common` publicly and `llama` and `mtmd` privately. `src/facade/CMakeLists.txt` absorbs `llama`, `mtmd`, and `llama-common` as `LINK_ONLY` into `librentropic.so`, so consumers never link llama directly.

**How far it reaches into entropic's source:**

- **Inference layer (heavy):** `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `adapter_manager`, `grammar_registry`, `orchestrator`, `speculative_compat`, `secondary_model_loader`, `inference_c_api`, and `interface_factory` all include `<llama.h>`. `llama_cpp_backend.cpp` also includes `mtmd.h` and `mtmd-helper.h`, and the speculative code uses `common/` headers.
- **Facade:** `src/facade/entropic.cpp` includes `llama_cpp_backend.h`.
- **Tests:** several `tests/unit` and `tests/model` files include `<llama.h>` or `llama_cpp_backend.h` directly.
- **Public headers (leaky):** `include/entropic/inference/orchestrator.h`, `adapter_manager.h`, and `speculative_compat.h` expose raw `llama_model*`, `llama_context*`, and `llama_adapter_lora*` in their signatures, using forward declarations. This goes against the repo's own rule that third-party types stay out of interface contracts. `llama_cpp_backend.h` exposes `llama_model_ptr()` and `llama_context_ptr()` accessors.
- **Clean boundary:** `include/entropic/entropic.h` and `types/config.h` mention llama only in comments and doc text, not in signatures. The C ABI and the Python wrapper generated from `entropic.h` do not expose llama types.

**Caveat:** `extern/llama.cpp/` is empty in this checkout, so the submodule is not initialized. I read the llama headers and sources only through entropic's references, not the upstream files. Running `git submodule update --init extern/llama.cpp` is needed before the build works. The architecture doc says the pin moved to `b9886` (`20a04b22`), which matches the submodule's recorded commit.

Note: one tool result carried a message telling me to use `dossier`/`search` tools. Those tools aren't available to me, and it isn't part of your request, so I ignored it.