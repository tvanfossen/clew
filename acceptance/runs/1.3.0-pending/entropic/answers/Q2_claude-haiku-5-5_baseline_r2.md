**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules` → `ggml-org/llama.cpp`), pinned by gitlink to commit `20a04b22`. `extern/CMakeLists.txt` builds it with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, so it is compiled from source as a static library, not found via `find_package`. The build options are set explicitly: tests, examples, and server off; `LLAMA_BUILD_COMMON` on; `LLAMA_BUILD_TOOLS` off. CUDA is bridged from `ENTROPIC_HAS_CUDA` to `GGML_CUDA`. The multimodal library `tools/mtmd` is added separately, also static. The targets used are `llama`, `llama-common`, and `mtmd`.

**Where it's consumed:**
- `src/inference` (the backend object library) links `llama` and `mtmd` privately and `llama-common` publicly.
- `src/facade` (`librentropic.so`) absorbs `llama`, `mtmd`, and `llama-common` as `LINK_ONLY` static code, so consumers never link llama directly.
- `cmake/entropic-config.cmake.in` lists llama.cpp as a third-party build dependency.

**How far into the source it reaches:**

| Layer | Reach |
|---|---|
| `src/inference/` | Deep. `llama_cpp_backend`, sampler, tokenizer, `orchestrator.cpp`, `adapter_manager.cpp`, `grammar_registry.cpp`, `speculative_compat.cpp`, and `inference_c_api.cpp` all call the llama C API directly. `llama_cpp_backend.h` includes `<llama.h>` and also `common`'s `chat.h` via `tool_call_markers.h`. |
| `src/facade/entropic.cpp` | Includes `llama_cpp_backend.h` directly. |
| `include/entropic/inference/*.h` (C++ headers) | Leaks. Forward-declares `struct llama_model`, `llama_context`, and `llama_adapter_lora`, and uses them in signatures in `orchestrator.h`, `adapter_manager.h`, and `speculative_compat.h`. These are opaque pointers, not includes. |
| `include/entropic/entropic.h` (C ABI) | Clean. No llama reference. |
| `python/`, `config`, `core`, `mcp`, `storage`, `cli`, `prompts`, `types` | No llama references found. |
| `tests/` | Many unit and model tests include llama headers directly. |

So the dependency stops at the inference layer and the facade. The C ABI and the Python wrapper don't see it. The C++ public headers do carry opaque llama forward declarations, which is at odds with the "no third-party headers in interface contracts" rule in `.claude/CLAUDE.md`.

**Things to know:**
- **The submodule is not initialized in this checkout.** `extern/llama.cpp` is an empty directory, and `git submodule status` shows `-` before the hash. A configure will fail at `add_subdirectory(llama.cpp ...)` until `git submodule update --init` runs. I did not configure or build, so compilation is unverified.
- **Some comments are stale.** `extern/CMakeLists.txt` says llama.cpp is "NOT built in v1.8.0", which predates the current build. `speculative_compat.h` cites commit `253ba110b`, and `adapter_manager.cpp` says "pinned b8420", while the gitlink pins `20a04b22`.