**Short answer:** llama.cpp comes in as a pinned git submodule that CMake builds from source and absorbs statically into `librentropic.so`. Its types reach the inference backend, the orchestrator, and the speculative and grammar code, and they also appear in a few public headers. They do not reach the C ABI (`entropic.h`) or the Python package.

**How it's brought in**

- `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`. The gitlink is pinned at `20a04b22` (`git ls-files -s`). In this checkout the directory is empty, so the submodule has not been initialized and a build will fail until `git submodule update --init` runs.
- `extern/CMakeLists.txt` is the only place it is wired in. It sets `LLAMA_BUILD_COMMON=ON` and `LLAMA_BUILD_TOOLS=OFF`, forces `BUILD_SHARED_LIBS=OFF`, then calls `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. A second `add_subdirectory` pulls in `llama.cpp/tools/mtmd` for multimodal. Every other dependency here uses FetchContent; llama.cpp is the only submodule. Its CUDA flag is bridged from `ENTROPIC_HAS_CUDA`.
- Link edges: `src/inference/CMakeLists.txt` links `llama-common` publicly and `llama` and `mtmd` privately. `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` into the facade, so they are absorbed into `librentropic.so`. The facade's private include dirs are `extern/llama.cpp/include` and `ggml/include`.

**How far it reaches into entropic source**

Direct `#include <llama.h>`, `<chat.h>`, `<sampling.h>`, `<mtmd.h>` and `<mtmd-helper.h>` appear in about 20 files, all under `src/inference/` or in tests:

| Area | Files | What they use |
|---|---|---|
| Backend | `llama_cpp_backend.cpp/.h` | Model/context lifecycle, `llama_decode`, mtmd, common chat, `common_sampler_*` |
| Sampler / tokenizer | `llama_cpp_sampler.cpp`, `llama_cpp_tokenizer.cpp` | `llama_sampler_chain`, vocab APIs |
| Orchestration | `orchestrator.cpp`, `adapter_manager.cpp`, `secondary_model_loader.cpp` | LoRA `llama_set_adapters_lora`, `llama_memory_*` |
| Speculative / grammar | `speculative_compat.cpp`, `grammar_registry.cpp`, `tool_call_markers.h` | Vocab checks, `llama_sampler_init_grammar`, `common_chat` |
| Facade | `src/facade/entropic.cpp` | Only reaches the backend through `dynamic_cast<LlamaCppBackend*>` and `llama_model_ptr()` |

The reach extends beyond the .cpp files. Several headers under `include/entropic/` forward-declare `struct llama_model` or `llama_context` and expose them in signatures:

- `include/entropic/inference/speculative_compat.h` takes `const llama_model*`.
- `include/entropic/inference/orchestrator.h` takes `llama_context*` and `llama_model*`.
- `include/entropic/inference/sampler.h` and `grammar_registry.h` also mention llama types.

Those are public C++ headers, so llama.cpp types are visible to C++ consumers of the interface headers. The C ABI (`include/entropic/entropic.h`) only mentions llama.cpp in comments about blob portability and error codes. `python/` has no llama references, so the Python wrapper is not affected.

**Things worth noting**

- The `CMakeLists` comment says "pinned at b8420", but the decision log says the pin moved to b9886 (`20a04b22`). The comment is stale.
- The decision log records real llama.cpp behavior (hybrid/recurrent speculative gating, `llama_memory_*` API use, the MTP argmax assumption) tied to the pin. Bumping the submodule can silently change those, and the log says so.
- I did not read the llama.cpp source itself, since the submodule is not checked out here.