**Short answer:** llama.cpp is a git submodule at `extern/llama.cpp`, built from source by CMake and absorbed statically into `librentropic.so`. Its reach is confined to the inference layer and a few facade and C++ headers, not the whole engine.

**How it's brought in**

- `.gitmodules` points at `ggml-org/llama.cpp`. The checkout here is empty: `git submodule status` shows the commit `20a04b22…` with a `-` prefix, so the submodule is not initialized. I could not inspect llama.cpp's own headers or build the project.
- `extern/CMakeLists.txt` calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` with these settings:
  - `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` = OFF, `LLAMA_BUILD_COMMON` = ON.
  - Static libraries, with position-independent code forced on.
  - `ENTROPIC_CUDA` is bridged to `GGML_CUDA`.
- It also adds `llama.cpp/tools/mtmd` for multimodal support, again with `EXCLUDE_FROM_ALL`.
- The source comments in that file are stale: they say llama.cpp is "NOT built in v1.8.0" and pin it to "b8420", but the code builds it.

**Where it is linked**

- `src/inference/CMakeLists.txt` builds the inference OBJECT library. It links `llama` and `mtmd` PRIVATE and `llama-common` PUBLIC, and includes llama.cpp's `vendor/` and `common/` directories.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` PRIVATE, so they are folded into `librentropic.so`. Consumers never link llama directly.

**How far it reaches into entropic's source**

| Layer | Reach |
|---|---|
| Build | Only `src/inference` and `src/facade`. `config`, `core`, `mcp`, `types` and `storage` do not depend on llama at build time. |
| Source | 12 files in `src/` include llama, ggml, mtmd or common headers. The 10 I measured total 13,486 lines, about 27% of the 49k lines in `src/`. |
| Public C++ headers (`include/entropic/inference/`) | No llama header is included, but `orchestrator.h`, `adapter_manager.h` and `speculative_compat.h` forward-declare `struct llama_model`, `llama_context` and `llama_adapter_lora`. Their methods take and return those raw pointers. |
| Public config and error types | `types/config.h` has llama.cpp pass-through fields and comments, and `error.h` mentions `llama_decode`. These are names and comments, not llama types. |
| C ABI (`entropic.h`) | Clean. llama appears only in comments, so no llama type crosses the `.so` boundary. |

**Takeaway:** the C ABI and the config, core, MCP and types layers are insulated. The leak is the C++ inference interface, where `llama_model*` and `llama_context*` are part of the orchestrator and adapter-manager signatures. That is worth checking against the "no third-party headers in interface contracts" rule in `docs/architecture-cpp.md`, though forward declarations are weaker than an include.

To verify the build and the header-level claims, run `git submodule update --init extern/llama.cpp` first.