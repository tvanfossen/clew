**Short answer:** llama.cpp is a git submodule that CMake builds in-tree and statically absorbs into `librentropic.so`. Its C API and its `common/` helpers reach into the inference layer and the facade. Consumers never link it directly. Entropic's public headers mostly stay clear of it, with a few exceptions noted below.

**How it's brought in**

- `.gitmodules` maps `extern/llama.cpp` to ggml-org/llama.cpp. The superproject pins it at `20a04b22…`.
- `extern/CMakeLists.txt` (`# ── llama.cpp`) sets `LLAMA_BUILD_COMMON=ON`, `LLAMA_BUILD_TOOLS=OFF`, and the example, test and server options OFF. It then runs `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` and a second `add_subdirectory` on `llama.cpp/tools/mtmd`. Both are built as static libraries (`BUILD_SHARED_LIBS` is forced OFF), and the CUDA/Vulkan variant is chosen by `GGML_CUDA`.
- `src/inference/CMakeLists.txt` builds the `entropic-inference-{cpu,cuda,vulkan}` OBJECT library. It links `llama-common` as PUBLIC and `llama` and `mtmd` as PRIVATE. Its private include paths include `extern/llama.cpp/common` and `vendor`.
- `src/facade/CMakeLists.txt` gives `entropic-facade` `$<LINK_ONLY:llama>`, `mtmd`, and `llama-common`. The comment says these are absorbed into the `.so` so they don't leak into the consumer-visible export. Its private includes are `extern/llama.cpp/include` and `ggml/include`.

**How far it reaches into entropic's source**

| Layer | Reach |
|---|---|
| `src/inference/` | Heavy. `llama_cpp_backend.{h,cpp}` includes `<llama.h>`, `<common.h>`, `<chat.h>`, `<sampling.h>`, `<speculative.h>`, `<mtmd.h>` and `<mtmd-helper.h>`. The sampler, tokenizer, `orchestrator.cpp`, `adapter_manager.cpp`, `speculative_compat.cpp`, `grammar_registry.cpp`, `inference_c_api.cpp`, and `tool_call_markers.h` also include llama headers. `LlamaCppBackend` is the concrete class of the layer, with `model_`, `ctx_` and `vocab_` as raw llama pointers. |
| `src/facade/entropic.cpp` | Includes `llama_cpp_backend.h` and calls `dynamic_cast<entropic::LlamaCppBackend*>` in three places (lines 2922, 2964, 2996). |
| `include/entropic/` (public) | No `#include` of llama or ggml headers. Instead, `orchestrator.h` and `speculative_compat.h` forward-declare `struct llama_context;` and `struct llama_model;`, and expose `llama_context*` and `llama_model*` in signatures such as `deactivate_if_active(llama_context*)`. `entropic.h` only mentions llama in comments. |
| Tests | Many unit and model tests include llama headers. Some unit tests mock llama symbols such as `llama_adapter_lora_init` and `llama_vocab_n_tokens`. |

**Things that stand out**

1. **The submodule is not initialized in this checkout.** `extern/llama.cpp/` is an empty directory, and `git submodule status` shows a leading `-`. The `rev-parse` output I initially read was the superproject's commit, because git walked up out of the empty directory. Unless the directory is populated by `git submodule update --init`, `add_subdirectory(llama.cpp)` will fail at configure time. I haven't run configure, so that is inferred from the CMake and filesystem state.
2. **The CMake comments are stale.** `extern/CMakeLists.txt` says llama.cpp "is NOT built in v1.8.0", and the backend comment says the pin is `b8420`. The code builds it now, and I did not check that `b8420` matches the `20a04b22` gitlink.
3. **The public-header boundary is leaky.** `CLAUDE.md` says "No third-party headers in interface contracts". Forward declarations plus raw `llama_*` pointer parameters in `orchestrator.h` and `speculative_compat.h` are a weaker form of that leak. They don't break the build, but they do expose llama types to consumers of the public C++ API.