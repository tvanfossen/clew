**How it's brought in**

llama.cpp is a git submodule at `extern/llama.cpp` (`.gitmodules`), pinned by gitlink to commit `20a04b22`. `extern/CMakeLists.txt` pulls it in with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)` and sets its options first: tests, examples, server and tools off, `LLAMA_BUILD_COMMON` on, and CUDA and CUDA graphs bridged from entropic's own flags. It also adds `llama.cpp/tools/mtmd` for multimodal support, again with `EXCLUDE_FROM_ALL`. Every other dependency in that file (spdlog, ryml, Catch2, json, httplib) comes through FetchContent; llama.cpp is the only one that comes from a submodule.

The facade then absorbs it. `src/facade/CMakeLists.txt` links `llama`, `mtmd` and `llama-common` as `$<LINK_ONLY:>` PRIVATE dependencies of `entropic-facade`, so they are statically folded into `librentropic.so` and do not appear in the consumer-facing export.

**How far it reaches into entropic's source**

Most of the reach is inside the inference layer, not the public surface:

- **Direct `#include <llama.h>` / `<common.h>` / `<mtmd.h>` etc.:** `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `speculative_compat.cpp`, `adapter_manager.cpp`, `orchestrator.cpp`, `grammar_registry.cpp`, and `tool_call_markers.h` (`chat.h`).
- **Indirect:** `interface_factory.cpp`, `secondary_model_loader.cpp`, `inference_c_api.cpp` and `facade/entropic.cpp` only include `llama_cpp_backend.h`, so they inherit llama types through it.
- **Llama types in headers:** `include/entropic/inference/orchestrator.h`, `adapter_manager.h` and `speculative_compat.h` forward-declare `llama_model`, `llama_context` and `llama_adapter_lora`, and take raw `llama_*` pointers in method signatures. `CLAUDE.md` says "no third-party headers in interface contracts." Forward declarations are not headers, but raw llama pointers in signatures still couple those interfaces to llama. I did not check whether `include/entropic/inference/` is installed as public API.
- **Not leaked:** the C API in `entropic.h` contains no llama types as far as the grep shows. Its `config.h` mentions are plain config fields (`ggml_logging`, `llama_log_path`).
- **Backend class:** `LlamaCppBackend` is the only place llama.cpp's model, context and KV-cache APIs are used; the rest of the engine goes through `InferenceBackend`.
- **Tests:** `tests/unit/inference/*` and `tests/model/*` reach llama directly, including the `*_for_test` seams.

**Things to check**

- The submodule is **not populated** in this checkout: `extern/llama.cpp/` is an empty directory. A build needs `git submodule update --init` first.
- The comments are stale. `extern/CMakeLists.txt` says "pinned at b8420", and `llama_cpp_backend.h` cites "pin 253ba110b". The actual gitlink is `20a04b22`. I did not check which of these commits matches the code, so the comments may still be right about an older pin.