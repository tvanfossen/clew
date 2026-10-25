**How it's brought in:** llama.cpp is a git submodule, not a FetchContent dependency. `.gitmodules` maps `extern/llama.cpp` to `ggml-org/llama.cpp`, and `extern/CMakeLists.txt:55-104` pulls it in with `add_subdirectory(llama.cpp EXCLUDE_FROM_ALL)`. It also adds `llama.cpp/tools/mtmd` for multimodal support, and sets `LLAMA_BUILD_COMMON=ON` so the `llama-common` target exists. `LLAMA_BUILD_TESTS`, `EXAMPLES`, `SERVER` and `TOOLS` are forced off. The other deps (spdlog, ryml, Catch2, nlohmann/json, cpp-httplib) come through FetchContent in the same file. llama.cpp is the only one built from a local submodule.

Build wiring:

- `src/inference/CMakeLists.txt` builds the `entropic-inference-{cpu,cuda,vulkan}` OBJECT library. The three `llama_cpp_*` sources are compiled there. `llama-common` is PUBLIC and `llama` and `mtmd` are PRIVATE.
- `src/facade/CMakeLists.txt:37-50` links `llama`, `mtmd` and `llama-common` as `LINK_ONLY` into `entropic-facade`, which produces `librentropic.so`. The comments say these are absorbed as static code, so consumers never link llama directly.

**How far it reaches into entropic's source:**

| Layer | Reach |
|---|---|
| `src/inference/` | Deep. Six files include `<llama.h>` directly: `llama_cpp_backend.{h,cpp}`, `llama_cpp_sampler`, `llama_cpp_tokenizer`, `orchestrator`, `adapter_manager`, `grammar_registry`, `speculative_compat`. `llama_cpp_backend.cpp` also includes llama.cpp `common/` headers (chat, sampling, speculative). `llama_cpp_backend.h` exposes `llama_model*`, `llama_context*` and `common_chat` types in its class interface. |
| `src/facade/` | Shallow but present. `entropic.cpp` includes llama headers, and the facade's private include paths point at `extern/llama.cpp/include` and `ggml/include`. |
| `src/core`, `cli`, `mcp`, `config`, `storage`, `prompts`, `python` | None. The only `llama_` hit is the config key `llama_log_path` in `src/config/loader.cpp:657`. |
| `include/entropic/` (public) | No `#include <llama.h>`, but several public headers leak llama types as opaque forward declarations. These are `struct llama_model/llama_context/llama_adapter_lora` in `orchestrator.h`, `adapter_manager.h` and `speculative_compat.h` (`speculative_compat.h:94` takes `const llama_model*` in a public signature), and `sampler.h` and `grammar_registry.h` mention llama types in comments and signatures. `entropic.h` only mentions llama.cpp in doc comments about state blobs. |
| `tests/` | Several unit and model tests include `<llama.h>` and link `llama` directly. |

So llama.cpp is compiled into and linked by the inference layer, and its types appear in internal and some public inference headers. The C ABI in `entropic.h` stays clean.

**Things to check:**

- The submodule is uninitialized in this checkout. `git submodule status` shows `-20a04b22…` (leading dash), and `extern/llama.cpp/` is empty. A build will fail until `git submodule update --init extern/llama.cpp` runs.
- The pin is described inconsistently. `extern/CMakeLists.txt` says "pinned at b8420", and `speculative_compat.h` says `253ba110b`. The checked-out commit is `20a04b22`. Those comments are stale or the pin has moved.
- The header comment in `extern/CMakeLists.txt:3` says llama.cpp "is NOT built in v1.8.0". That is outdated, since it is built now.