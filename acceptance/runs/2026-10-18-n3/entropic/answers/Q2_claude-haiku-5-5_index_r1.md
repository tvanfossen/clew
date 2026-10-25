**How it's brought in:** llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules` points at `ggml-org/llama.cpp`). It is not a FetchContent dependency like spdlog, ryml, Catch2, nlohmann/json and httplib, which `extern/CMakeLists.txt` fetches at configure time. The submodule is built from source in that same file (`extern/CMakeLists.txt:55-103`):

- `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`, with `LLAMA_BUILD_TESTS/EXAMPLES/SERVER/TOOLS` forced OFF and `LLAMA_BUILD_COMMON` forced ON.
- `BUILD_SHARED_LIBS` forced OFF for the duration, so llama is static.
- A second subdirectory, `llama.cpp/tools/mtmd`, is added explicitly for multimodal support.
- `EXCLUDE_FROM_ALL` suppresses llama's install rules, because the comment says consumers never link llama directly.

Those targets are then wired in by link lines:

- `src/inference/CMakeLists.txt:64-70`: the inference OBJECT library links `llama-common` PUBLIC and `llama` and `mtmd` PRIVATE.
- `src/facade/CMakeLists.txt:33-52`: `librentropic` absorbs `llama`, `mtmd` and `llama-common` as `$<LINK_ONLY:>` PRIVATE dependencies, so they end up statically inside the shared library.
- Unit and model tests link `llama` directly and add `extern/llama.cpp/common` to their include paths.

**How far it reaches into entropic's source:**

| Layer | Touches llama? |
|---|---|
| `src/inference/` | Deep. `llama.h` is included directly by `llama_cpp_backend.cpp/.h`, `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp`, `orchestrator.cpp`, `adapter_manager.cpp`, `speculative_compat.cpp` and `grammar_registry.cpp`. `llama_cpp_backend.cpp` also pulls in `common.h`, `chat.h`, `sampling.h`, `speculative.h`, `mtmd.h` and `mtmd-helper.h`. `tool_call_markers.h` includes `chat.h`. `LlamaCppBackend` exposes raw `llama_model*`, `llama_context*` and `llama_vocab*` through accessors. |
| `src/facade/entropic.cpp`, `inference_c_api.cpp`, `interface_factory.cpp`, `secondary_model_loader.cpp` | Transitively. They include `llama_cpp_backend.h`, so they compile against llama types. The C API surface itself still exposes only opaque handles. |
| `include/entropic/` (public headers) | Only forward declarations: `struct llama_model;` and similar in `adapter_manager.h`, `orchestrator.h` and `grammar_registry.h`. There are no `#include`s of llama headers. Mentions in `entropic.h` are comments. |
| `src/core`, `src/config`, Python wrapper | No llama includes. `config/loader.cpp` and `config_schema.json` only carry the `ggml_logging` and `llama_log_path` settings. |

So the dependency stops at the inference layer. Llama types are confined to the `.so` and kept out of the public C ABI, which matches design rule 1 in `CLAUDE.md` ("pure C at all `.so` boundaries") and the architecture doc's "no third-party headers in interface contracts".

**Things you should know:**

- **The checkout can't build as-is.** `git submodule status` shows `-20a04b22… extern/llama.cpp` (uninitialised), and `extern/llama.cpp/` is an empty directory. You need `git submodule update --init` before CMake will configure. I didn't run CMake, so I haven't confirmed the rest of the build.
- **Pin mismatch to check.** The comments everywhere say the pin is b8420, but the gitlink recorded in the superproject is `20a04b22`. I couldn't verify which commit that is without the submodule checked out.