**Short answer:** llama.cpp is vendored as a git submodule and compiled statically into `librentropic.so` through CMake. It reaches into entropic's source only in the `src/inference/` layer and the facade. The public headers under `include/` never include llama.cpp headers.

**How it's brought in**

- `.gitmodules` registers `extern/llama.cpp` (from ggml-org/llama.cpp).
- `extern/CMakeLists.txt` sets the llama.cpp options (tests, examples, server and tools off, `LLAMA_BUILD_COMMON` on, `BUILD_SHARED_LIBS` off), then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal. The other dependencies (spdlog, ryml, json, httplib, Catch2) use `FetchContent`, but llama.cpp does not.
- `src/inference/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as PRIVATE, and `llama-common` as PUBLIC on the inference object library. Its private include dirs point into `extern/llama.cpp/vendor` and `common`.
- `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` into `entropic-facade`, so they are absorbed into the shared library. The facade also adds `extern/llama.cpp/include` and `ggml/include` to its include path.

**How far it reaches**

| Layer | Touches llama.cpp? | Evidence |
|---|---|---|
| `include/entropic/*` (public C API and headers) | No `#include`s. Only comments, `struct llama_model;` forward declarations, and config field names that mirror llama.cpp parameters. | `orchestrator.h:44`, `adapter_manager.h:36`, `speculative_compat.h:47` |
| `src/inference/llama_cpp_*.{h,cpp}` | Yes, directly. `llama_cpp_backend.h:33` includes `<llama.h>`, and the `.cpp` also includes `<mtmd.h>` and `<mtmd-helper.h>`. | `llama_cpp_backend.cpp:31-32` |
| Other `src/inference/` files | Yes, direct `<llama.h>` includes in `speculative_compat`, `adapter_manager`, `orchestrator`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `grammar_registry`. | grep results |
| `src/inference/inference_c_api.cpp`, `src/facade/entropic.cpp`, `interface_factory.cpp`, `secondary_model_loader.cpp` | Indirectly. They include `llama_cpp_backend.h` and reach llama types through `LlamaCppBackend`, e.g. `llama_model_ptr()` and `llama_context_ptr()` in `entropic.cpp:2922-3001`. | grep results |

The index holds seven llama-named source files in `src/inference/`. `LlamaCppBackend` (`llama_cpp_backend.h:65`) is the main consumer. It exposes `llama_model*` and `llama_context*` accessors and owns `model_`, `ctx_` and `vocab_` (lines 633-635). It also uses the common-chat, speculative and mtmd APIs.

So the boundary is: llama.cpp types stop at `src/inference/`. The C API and the Python wrapper see only opaque handles and entropic types. This matches the design rule "Pure C at all `.so` boundaries" in `CLAUDE.md`.

**Things to know**

- The `extern/llama.cpp` directory is empty in this checkout, so the submodule is not initialized. The build cannot succeed here until `git submodule update --init` runs. I did not check the pinned commit.
- The pin is documented inconsistently. `extern/CMakeLists.txt` says "pinned at b8420", while `speculative_compat.h` says "v2.1.11-pinned commit `253ba110b`". Either the pin moved or one comment is stale.
- The comment in `extern/CMakeLists.txt` that says "llama.cpp is a submodule but NOT built in v1.8.0" is stale. It is built now.