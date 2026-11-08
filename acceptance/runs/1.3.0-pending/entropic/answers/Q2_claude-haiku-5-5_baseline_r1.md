**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`), pinned at b8420 per the comment in `extern/CMakeLists.txt`. Unlike spdlog, ryml, json, httplib and Catch2, it is not a FetchContent dependency. `extern/CMakeLists.txt` calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` with these settings:

- Static build (`BUILD_SHARED_LIBS` forced OFF).
- `LLAMA_BUILD_TESTS`, `EXAMPLES`, `SERVER` and `TOOLS` all OFF. `LLAMA_BUILD_COMMON` is ON so the `common` target exists.
- `GGML_CUDA` is set from `ENTROPIC_HAS_CUDA`.
- A second `add_subdirectory` pulls in only `llama.cpp/tools/mtmd` for multimodal support.

Linking:

- `src/inference/CMakeLists.txt` builds the inference code as an OBJECT library. `llama-common` is PUBLIC, and `llama` and `mtmd` are PRIVATE.
- `src/facade/CMakeLists.txt` absorbs `llama`, `mtmd` and `llama-common` statically into `librentropic.so` as `LINK_ONLY` dependencies. Consumers never link llama directly.

**How far it reaches into source:**

| Layer | Reach |
|---|---|
| `src/inference/` | Heavy. Nine files include a llama.cpp header directly (`llama.h`, `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h`). These are `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `orchestrator`, `adapter_manager`, `grammar_registry`, `speculative_compat` and `tool_call_markers.h`. Four more reach llama only through `llama_cpp_backend.h`: `interface_factory`, `secondary_model_loader`, `inference_c_api` and the facade's `entropic.cpp`. |
| `src/core`, `mcp`, `config`, `storage`, `cli`, `prompts`, `types` | None. Grep found no llama or ggml includes there. |
| `include/entropic/*.h` (C ABI, `entropic.h`) | No llama includes. llama.cpp is mentioned only in comments, such as the state-blob notes around line 928. |
| `include/entropic/inference/*.h` (C++ interfaces) | Forward declarations and pointer types. `orchestrator.h` declares `struct llama_context;` and `struct llama_model;` and has methods taking `llama_context*` (e.g. `deactivate_if_active`, line 759). `speculative_compat.h` takes `const llama_model*`. `grammar_registry.h` and `sampler.h` refer to llama types too. |
| `python/` | None. The wrapper is generated from `entropic.h`. |
| `tests/unit`, `tests/model` | Direct includes in several unit tests (`grammar_engagement`, `vocab_only_smoke`, `speculative_compat`, `inference_c_api`), plus many model tests. |

So the C ABI is clean, but llama types leak into the C++ interface headers as opaque pointers. That conflicts with the "no third-party headers in interface contracts" rule in `.claude/CLAUDE.md`. Forward-declaring a foreign type is a weaker breach than including its header, but it is still a breach.

**Things to note:**

- **The submodule is empty in this checkout.** `extern/llama.cpp` is an empty directory and `git submodule status` shows it uninitialised (`-`). A configure will fail until `git submodule update --init --recursive` is run. CI already uses `submodules: recursive`.
- **A comment in `extern/CMakeLists.txt` is stale.** It says llama.cpp is "NOT built in v1.8.0", but the file now builds it.