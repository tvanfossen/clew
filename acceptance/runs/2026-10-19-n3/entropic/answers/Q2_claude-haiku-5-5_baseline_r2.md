**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`, pinned at commit `20a04b22`). It is not fetched via FetchContent like spdlog, ryml, Catch2, nlohmann/json and cpp-httplib, which are declared in the same `extern/CMakeLists.txt`. The CMake file sets the llama build options (`LLAMA_BUILD_COMMON=ON`, `LLAMA_BUILD_TOOLS=OFF`, tests/examples/server off, CUDA bridged from `ENTROPIC_HAS_CUDA`) and then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal support. Everything is compiled as static code and absorbed into the entropic shared libraries; nothing is installed or exported to consumers.

**Where it's linked:**
- `src/inference/CMakeLists.txt` links `llama`, `mtmd` and `nlohmann_json` PRIVATE, and `llama-common` PUBLIC.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` PRIVATE, so they resolve at the `.so` link step.

**How far it reaches into entropic's source:** the reach is wide. The C++ backend uses it directly and several modules touch it.

| Layer | Reach |
|---|---|
| `src/inference/` | Direct. `llama_cpp_backend`, `_sampler`, `_tokenizer`, `speculative_compat`, `adapter_manager`, `grammar_registry`, `orchestrator`, `inference_c_api`, `interface_factory`, `secondary_model_loader`. Includes `<llama.h>`, `<chat.h>`, `<common.h>`, `<sampling.h>`, `<speculative.h>`, `<mtmd.h>`, `<mtmd-helper.h>`, and `tool_call_markers.h` pulls in `chat.h`. |
| `src/facade/entropic.cpp` | Includes `llama_cpp_backend.h`. It `dynamic_cast`s to `LlamaCppBackend` and calls `llama_model_ptr()` / `llama_context_ptr()` to drive adapter load, unload and swap. |
| `src/config/loader.cpp` | Only config keys (`ggml_logging`, `llama_log_path`). No llama.cpp types. |
| `include/entropic/` (public) | No llama headers, but llama.cpp types leak as forward declarations: `llama_model`, `llama_context`, `llama_adapter_lora` appear in `orchestrator.h`, `adapter_manager.h`, `speculative_compat.h`, and the `sampler.h` / `grammar_registry.h` docs. Consumers see the names, not the headers. |
| Tests | `tests/unit/inference/*` and `tests/model/*` include `<llama.h>` and `<chat.h>` directly. |

**Observations:**
- The design rule "no third-party headers in interface contracts" is kept at the header level, but the public API still names llama.cpp structs, so a consumer cannot use those signatures without llama.cpp's type names being in scope.
- The `llama-common` PUBLIC link in `src/inference` propagates to anything that links the inference target. The facade's `LINK_ONLY` suggests this was meant to stay internal, so it is worth checking whether it is needed.
- The comment at the top of `extern/CMakeLists.txt` ("NOT built in v1.8.0") is stale. The code now builds llama.cpp.