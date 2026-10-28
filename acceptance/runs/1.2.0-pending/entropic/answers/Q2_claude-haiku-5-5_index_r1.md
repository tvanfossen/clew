**How it's brought in:** llama.cpp is a vendored git submodule at `extern/llama.cpp`, pinned by gitlink to commit `20a04b22` (`.gitmodules`). It is not a FetchContent dependency like spdlog, ryml, json or httplib. `extern/CMakeLists.txt` builds it at configure time with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, after forcing its options: no tests, examples, server or tools, `LLAMA_BUILD_COMMON=ON`, and `GGML_CUDA` bridged from `ENTROPIC_HAS_CUDA`. It also adds `llama.cpp/tools/mtmd` for multimodal. Both are built static, and `EXCLUDE_FROM_ALL` stops llama.cpp's own install rules from firing.

```
extern/llama.cpp (submodule)
   ├── llama      (libllama + ggml)
   ├── llama-common
   └── mtmd
          │  $<LINK_ONLY:...> PRIVATE
          ▼
src/inference  (OBJECT lib: PRIVATE llama, mtmd; PUBLIC llama-common)
          │
          ▼
src/facade     (entropic-facade → librentropic.so; absorbs them statically)
```

**How far it reaches:** it is contained in the implementation layer, with a few leaks.

- **Implementation, `src/inference/`:** this is where the code uses llama.cpp directly. `llama.h` is included by `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `grammar_registry.cpp`, `orchestrator.cpp`, `speculative_compat.cpp` and `adapter_manager.cpp`. `llama_cpp_backend.cpp` also pulls in `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h` and `mtmd-helper.h`. `tool_call_markers.h` includes `chat.h`.
- **`LlamaCppBackend`** (`src/inference/llama_cpp_backend.h:65`) is the main carrier. It owns `model_`, `ctx_`, `vocab_` and the mtmd context. It exposes raw `llama_model_ptr()` and `llama_context_ptr()` accessors, and its `CommonChatResult` wraps common_chat parse output. The rest of entropic sees it only as an `InferenceBackend`. `do_backend_name()` returns `"llama.cpp"`.
- **Facade, `src/facade/entropic.cpp`:** the one place outside `src/inference` that touches it. It includes `llama_cpp_backend.h` (the facade gets `src/inference` as a private include dir) and uses the raw pointers to wire LoRA adapters through `dynamic_cast<LlamaCppBackend*>`.
- **Public headers, `include/entropic/`:** these do not include any llama.cpp header. They forward-declare `struct llama_model`, `llama_context` and `llama_adapter_lora`, and the C ABI in `entropic.h` has no llama types. Config enums such as `llama_split_mode` are re-declared as entropic's own types. Two leaks remain. `adapter_manager.h:181-182` puts raw `llama_adapter_lora*` and `llama_model*` into a public struct, and `orchestrator.h` and `speculative_compat.h` take raw llama pointers in their signatures. The architecture doc says "No third-party headers in interface contracts". Forward declarations are not headers, but the spirit is broken.
- **Tests:** `tests/unit/inference` and `tests/model` include `llama.h` and `chat.h` directly, which is expected for seam tests.

**Things to know:**

- The submodule is not checked out in this copy. `extern/llama.cpp` is empty (the gitlink exists, `git submodule status` shows the commit). Nothing here will build until `git submodule update --init` runs. I did not build it.
- The pin is described inconsistently. `extern/CMakeLists.txt` says "pinned at b8420", the gitlink is `20a04b22`, and `llama_cpp_backend.cpp` and `speculative_compat.h` cite older commits (`253ba110b`, `7f2cbd9a4`). At least some of those comments are stale.